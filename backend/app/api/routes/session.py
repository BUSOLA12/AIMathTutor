import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.schemas import (
    AdvanceResponse,
    DeliveryPackage,
    EvaluationAnswerRequest,
    EvaluationResult,
    InterruptionRequest,
    ResumeCursor,
    SessionCreateRequest,
    SessionResponse,
    SessionState,
)
from app.models.tables import Session as SessionTable
from app.modules.evaluation.handler import score_evaluation
from app.modules.input_understanding.handler import understand_input
from app.modules.tutoring_delivery.delivery import (
    build_resume_package,
    prefetch_section_package,
)
from app.modules.tutoring_delivery.store import get_audio_clip
from app.session.manager import get_session_state, save_session_state

router = APIRouter()
logger = logging.getLogger(__name__)


def _graph_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _coerce_package(payload: dict | None) -> DeliveryPackage | None:
    if not payload:
        return None
    return DeliveryPackage(**payload)


async def _safe_prefetch(
    *,
    session_id: str,
    topic: str,
    learner_level: str,
    teaching_strategy: str,
    lesson_plan: dict,
    messages: list[dict],
    next_index: int,
) -> None:
    try:
        sections = lesson_plan.get("sections", [])
        if next_index >= len(sections):
            return

        await prefetch_section_package(
            session_id=session_id,
            topic=topic,
            learner_level=learner_level,
            teaching_strategy=teaching_strategy,
            section=sections[next_index],
            messages=messages,
            section_index=next_index,
        )
    except Exception as exc:  # pragma: no cover - background task safety
        logger.warning("Section prefetch failed for %s[%s]: %s", session_id, next_index, exc)


def _schedule_next_prefetch(state: SessionState, lesson_plan: dict, messages: list[dict], next_index: int) -> None:
    sections = lesson_plan.get("sections", [])
    if next_index >= len(sections):
        return

    asyncio.create_task(
        _safe_prefetch(
            session_id=state.session_id,
            topic=state.topic,
            learner_level=state.learner_level or "beginner",
            teaching_strategy=state.teaching_strategy or "intuition_first",
            lesson_plan=lesson_plan,
            messages=messages,
            next_index=next_index,
        )
    )


def _advance_response(
    *,
    session_id: str,
    phase: str,
    section: str | None = None,
    content: str | None = None,
    package: DeliveryPackage | None = None,
    evaluation_questions: list[str] | None = None,
    lesson_sections: list[str] | None = None,
    resume_pending: bool = False,
) -> AdvanceResponse:
    return AdvanceResponse(
        session_id=session_id,
        phase=phase,
        section=section,
        content=content,
        board_events=[],
        delivery_package=package,
        evaluation_questions=evaluation_questions,
        lesson_sections=lesson_sections,
        resume_pending=resume_pending,
    )


@router.post("/create", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    session_id = str(uuid.uuid4())
    result = await understand_input(request.input_text, session_id)

    db.add(
        SessionTable(
            id=session_id,
            topic=result.topic,
            target_type=result.target_type,
            subject_area=result.subject_area,
            phase="diagnosing",
        )
    )
    await db.commit()

    await save_session_state(
        SessionState(
            session_id=session_id,
            topic=result.topic,
            target_type=result.target_type,
            subject_area=result.subject_area,
            phase="diagnosing",
        )
    )

    return result


@router.get("/{session_id}/state", response_model=SessionState)
async def get_state(session_id: str):
    state = await get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


@router.get("/{session_id}/audio/{clip_id}")
async def get_session_audio(session_id: str, clip_id: str):
    clip = await get_audio_clip(session_id, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Audio clip not found")

    return Response(
        content=clip["audio_bytes"],
        media_type=clip["media_type"],
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{session_id}/interrupt", response_model=AdvanceResponse)
async def interrupt_session(session_id: str, request: InterruptionRequest):
    from app.modules.tutoring_delivery.graph import tutor_graph

    state = await get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.phase != "teaching":
        raise HTTPException(status_code=400, detail="Interruptions are only available during the lesson")

    state.interruptions_count += 1
    state.interruption_text = request.question_text
    if request.package_id:
        state.resume_cursor = ResumeCursor(
            package_id=request.package_id,
            section=state.current_section or "lesson",
            step_id=request.step_id,
            audio_offset_ms=max(0, request.audio_offset_ms),
        )
        state.resume_pending = True
    else:
        state.resume_cursor = None
        state.resume_pending = False
    await save_session_state(state)

    config = _graph_config(session_id)
    tutor_graph.update_state(
        config,
        {"interruption_pending": True, "interruption_text": request.question_text},
    )
    result = await tutor_graph.ainvoke(None, config=config)

    package = _coerce_package(result.get("delivery_package"))
    graph_phase = result.get("phase", "teaching")
    messages = result.get("messages", [])
    latest_message = messages[-1] if messages else None

    state.phase = graph_phase
    state.interruption_text = ""
    state.current_section = latest_message.get("section") if latest_message else state.current_section
    if package:
        state.current_package_id = package.package_id
        state.current_step_id = package.resume_cursor.step_id
        state.board_state_version += 1
    await save_session_state(state)

    return _advance_response(
        session_id=session_id,
        phase=graph_phase,
        section=package.section if package else state.current_section,
        content=package.transcript if package else None,
        package=package,
        resume_pending=state.resume_pending,
    )


@router.post("/{session_id}/advance", response_model=AdvanceResponse)
async def advance_session(session_id: str):
    """Drive the tutoring flow one package forward."""
    from app.modules.tutoring_delivery.graph import tutor_graph

    state = await get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if state.resume_pending and state.resume_cursor:
        package = await build_resume_package(session_id, state.resume_cursor)
        state.resume_pending = False
        state.resume_cursor = None
        state.phase = "teaching"
        if package:
            state.current_package_id = package.package_id
            state.current_step_id = package.resume_cursor.step_id
            state.current_section = package.section
            state.board_state_version += 1
        await save_session_state(state)

        if package:
            return _advance_response(
                session_id=session_id,
                phase="teaching",
                section=package.section,
                content=package.transcript,
                package=package,
            )

    config = _graph_config(session_id)

    if state.phase == "planning":
        initial: dict = {
            "session_id": session_id,
            "topic": state.topic,
            "subject_area": state.subject_area,
            "target_type": state.target_type,
            "learner_level": state.learner_level or "beginner",
            "missing_prerequisites": state.missing_prerequisites,
            "misconceptions": state.misconception_labels,
            "teaching_strategy": state.teaching_strategy or "intuition_first",
            "lesson_plan": {},
            "current_section_index": 0,
            "messages": [],
            "board_events": [],
            "delivery_package": None,
            "interruption_pending": False,
            "interruption_text": "",
            "evaluation_questions": [],
            "phase": "planning",
        }
        result = await tutor_graph.ainvoke(initial, config=config)
    else:
        result = await tutor_graph.ainvoke(None, config=config)

    graph_phase: str = result.get("phase", "teaching")
    lesson_plan: dict = result.get("lesson_plan", {})
    eval_questions: list = result.get("evaluation_questions", [])
    messages: list = result.get("messages", [])
    latest_message = messages[-1] if messages else None
    package = _coerce_package(result.get("delivery_package"))
    current_section_index = result.get("current_section_index", state.current_section_index)

    state.phase = graph_phase
    state.interruption_text = ""
    state.current_section_index = current_section_index
    state.current_section = latest_message.get("section") if latest_message else state.current_section
    if package:
        state.current_package_id = package.package_id
        state.current_step_id = package.resume_cursor.step_id
        state.board_state_version += 1
    await save_session_state(state)

    if package and package.section != "interruption" and lesson_plan:
        _schedule_next_prefetch(state, lesson_plan, messages, current_section_index)

    if graph_phase == "done":
        return _advance_response(
            session_id=session_id,
            phase=graph_phase,
            section=latest_message.get("section") if latest_message else None,
            content=latest_message.get("content") if latest_message else None,
            evaluation_questions=eval_questions or None,
            lesson_sections=lesson_plan.get("sections") if lesson_plan else None,
        )

    return _advance_response(
        session_id=session_id,
        phase=graph_phase,
        section=package.section if package else (latest_message.get("section") if latest_message else None),
        content=package.transcript if package else (latest_message.get("content") if latest_message else None),
        package=package,
        lesson_sections=lesson_plan.get("sections") if lesson_plan else None,
    )


@router.post("/evaluate", response_model=EvaluationResult)
async def submit_evaluation(request: EvaluationAnswerRequest):
    state = await get_session_state(request.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await score_evaluation(
        session_id=request.session_id,
        topic=state.topic,
        learner_level=state.learner_level or "unknown",
        questions=request.questions,
        answers=request.answers,
    )

    state.phase = "done"
    await save_session_state(state)
    return result
