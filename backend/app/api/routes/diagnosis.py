import logging
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.schemas import (
    DiagnosticAnswerRequest,
    DiagnosticQuestionResponse,
    DiagnosisResult,
)
from app.modules.diagnosis.background import (
    JOB_TYPE_GENERATED_ANALYSIS,
    JOB_TYPE_TRAINING_MATERIALIZATION,
    enqueue_diagnosis_background_job,
)
from app.modules.diagnosis.handler import (
    generate_diagnostic_question_batch,
    run_diagnosis_with_shadow,
)
from app.modules.diagnosis.store import (
    create_question_batch,
    get_latest_issued_question_batch,
    get_latest_question_batch,
    get_question_batch,
    mark_question_batch_submitted,
    persist_diagnosis_submission,
)
from app.modules.diagnosis.taxonomy import canonicalize_questions_with_overlay, normalize_topic_key
from app.session.manager import (
    delete_diagnosis_question_batch_ref,
    get_diagnosis_question_batch_ref,
    get_session_state,
    save_diagnosis_question_batch_ref,
    save_session_state,
)

router = APIRouter()
logger = logging.getLogger(__name__)
T = TypeVar("T")


def _canonicalization_status(canonical_question_ids: list[str | None]) -> str:
    if canonical_question_ids and all(canonical_question_ids):
        return "completed"
    if any(canonical_question_ids):
        return "partial"
    return "unresolved"


def _pad_optional_list(values: list[T] | None, length: int) -> list[T | None]:
    padded = list(values or [])
    if len(padded) < length:
        padded.extend([None] * (length - len(padded)))
    return padded[:length]


async def _get_reusable_question_batch(db: AsyncSession, session_id: str):
    batch_id = await get_diagnosis_question_batch_ref(session_id)
    if batch_id is not None:
        batch = await get_question_batch(db, batch_id)
        if batch is not None and batch.status == "issued":
            return batch

    batch = await get_latest_issued_question_batch(db, session_id)
    if batch is not None:
        await save_diagnosis_question_batch_ref(session_id, batch.id)
    return batch


async def _get_submittable_question_batch(db: AsyncSession, session_id: str):
    batch_id = await get_diagnosis_question_batch_ref(session_id)
    if batch_id is not None:
        batch = await get_question_batch(db, batch_id)
        if batch is not None:
            return batch

    batch = await get_latest_issued_question_batch(db, session_id)
    if batch is None:
        batch = await get_latest_question_batch(db, session_id)

    if batch is not None:
        await save_diagnosis_question_batch_ref(session_id, batch.id)
    return batch


@router.get("/{session_id}/questions", response_model=DiagnosticQuestionResponse)
async def get_questions(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    state = await get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    existing_batch = await _get_reusable_question_batch(db, session_id)
    if existing_batch is not None:
        return DiagnosticQuestionResponse(
            session_id=session_id,
            questions=list(existing_batch.questions or []),
        )

    subject_area = state.subject_area or "real_analysis"
    generated = await generate_diagnostic_question_batch(
        topic=state.topic,
        subject_area=subject_area,
        prerequisites=[],
    )

    question_count = len(generated.questions)
    canonical_question_ids: list[str | None] = []
    canonical_sources: list[str | None] = []
    canonical_scores: list[float | None] = []
    canonicalization_status = "pending"

    if generated.source != "llm_generated":
        matches = await canonicalize_questions_with_overlay(
            db,
            subject_area,
            state.topic,
            generated.questions,
        )
        canonical_question_ids = [match.template_id if match else None for match in matches]
        canonical_sources = [match.template_source if match else None for match in matches]
        canonical_scores = [round(match.score, 4) if match else None for match in matches]
        canonicalization_status = _canonicalization_status(canonical_question_ids)

    batch = await create_question_batch(
        db,
        session_id=session_id,
        topic=state.topic,
        topic_key=normalize_topic_key(state.topic),
        subject_area=subject_area,
        source=generated.source,
        questions=generated.questions,
        canonicalization_status=canonicalization_status,
        canonical_question_ids=canonical_question_ids,
        canonical_sources=canonical_sources,
        canonical_scores=canonical_scores,
    )
    await db.commit()
    await save_diagnosis_question_batch_ref(session_id, batch.id)

    if generated.source == "llm_generated":
        try:
            await enqueue_diagnosis_background_job(
                db,
                job_type=JOB_TYPE_GENERATED_ANALYSIS,
                session_id=session_id,
                question_batch_id=batch.id,
                payload={"source": generated.source, "question_count": question_count},
            )
        except Exception as exc:  # pragma: no cover - non-blocking producer safety
            logger.warning("Diagnosis generated-question analysis enqueue failed for %s: %s", session_id, exc)

    return DiagnosticQuestionResponse(session_id=session_id, questions=generated.questions)


@router.post("/submit", response_model=DiagnosisResult)
async def submit_answers(
    request: DiagnosticAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    state = await get_session_state(request.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    batch = await _get_submittable_question_batch(db, request.session_id)
    if batch is None or not batch.questions:
        raise HTTPException(
            status_code=409,
            detail="Diagnosis question batch not found. Request diagnostic questions again before submitting answers.",
        )

    subject_area = batch.subject_area or state.subject_area or "real_analysis"
    questions = list(batch.questions or [])
    live_result, live_model_source, shadow = await run_diagnosis_with_shadow(
        session_id=request.session_id,
        topic=state.topic,
        subject_area=subject_area,
        prerequisites=[],
        questions=questions,
        answers=request.answers,
        response_times_sec=request.response_times_sec,
        confidence_self_report=request.confidence_self_report,
    )

    canonical_question_ids = _pad_optional_list(batch.canonical_question_ids, len(questions))
    run = await persist_diagnosis_submission(
        db,
        session_id=request.session_id,
        question_batch_id=batch.id,
        topic=state.topic,
        subject_area=subject_area,
        questions=questions,
        answers=request.answers,
        response_times_sec=request.response_times_sec,
        canonical_question_ids=canonical_question_ids,
        confidence_self_report=request.confidence_self_report,
        live_result=live_result,
        live_model_source=live_model_source,
        shadow_model_source=shadow.source,
        shadow_model_confidence=shadow.confidence,
        shadow_result=shadow.prediction,
        shadow_status=shadow.status,
    )
    await mark_question_batch_submitted(db, batch)
    await db.commit()
    await delete_diagnosis_question_batch_ref(request.session_id)

    try:
        await enqueue_diagnosis_background_job(
            db,
            job_type=JOB_TYPE_TRAINING_MATERIALIZATION,
            session_id=request.session_id,
            diagnosis_run_id=run.id,
            payload={"question_batch_id": batch.id, "source": batch.source},
        )
    except Exception as exc:  # pragma: no cover - non-blocking producer safety
        logger.warning("Diagnosis training materialization enqueue failed for %s: %s", request.session_id, exc)

    state.learner_level = live_result.learner_level.value
    state.missing_prerequisites = live_result.missing_prerequisites
    state.teaching_strategy = live_result.recommended_teaching_strategy.value
    state.misconception_labels = live_result.misconception_labels
    state.phase = "planning"
    await save_session_state(state)

    return live_result
