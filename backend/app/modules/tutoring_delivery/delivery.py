import logging
import re
import uuid
from dataclasses import dataclass
from typing import Callable, Sequence

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.models.schemas import (
    AudioMarker,
    DeliveryPackage,
    DeliveryStep,
    ResumeCursor,
)
from app.modules.tutoring_delivery.speech import _estimate_marker_times, synthesize_package_audio
from app.modules.tutoring_delivery.store import (
    get_delivery_package,
    get_prefetched_package,
    pop_prefetched_package,
    save_audio_clip,
    save_delivery_package,
)

logger = logging.getLogger(__name__)

SECTION_PACKAGE_PROMPT = """You are building a live whiteboard delivery package for a math tutor.

Topic: {topic}
Student level: {learner_level}
Teaching strategy: {teaching_strategy}
Current section: {section}

### Conversation History
The following is the exact transcript of what you and the student have discussed so far:
{conversation_history}

Generate a JSON object with a "steps" list. Each step must include:
- kind: "heading" | "text" | "math" | "highlight" | "pause"
- display_text: what appears on the whiteboard
- spoken_text: what the tutor says at this step
- reveal_mode: "token" | "line" | "instant"
- target: optional target label for highlight steps

Rules:
- Produce 3 to 6 steps.
- Use exactly one heading step at the start unless the section is obviously too small.
- Put standalone formulas into math steps using complete LaTeX such as $$...$$.
- Do not split LaTeX across multiple steps.
- For math steps, spoken_text must explain the notation in plain English and must not include raw LaTeX markers such as $, _, ^, or commands like \\mathbb.
- Text steps should be prose-first, concise, and easy to reveal token-by-token.
- Use highlight only to emphasize a previously written step.
- Spoken text should sound like a tutor speaking naturally, not reading labels.
- DO NOT summarize or repeat the contents of the previous sections. Teach the new section based on the context.
"""

def _format_conversation_history(messages: Sequence[dict]) -> str:
    if not messages:
        return "(No conversation history yet. This is the start of the lesson.)"
    
    formatted = []
    for msg in messages:
        role = "Tutor" if msg.get("role") == "tutor" else "Student"
        formatted.append(f"{role}: {msg.get('content', '')}")
    return "\n\n".join(formatted)

INTERRUPTION_PACKAGE_PROMPT = """You are building a short interruption response package for a live math tutor.

Topic: {topic}
Current lesson section: {section}
Student question: {question}

Generate a JSON object with a "steps" list. Each step must include:
- kind: "heading" | "text" | "math" | "highlight" | "pause"
- display_text: what appears on the whiteboard
- spoken_text: what the tutor says
- reveal_mode: "token" | "line" | "instant"
- target: optional target label for highlight steps

Rules:
- Produce 2 to 4 steps.
- Answer directly, then end with a short bridge back to the lesson.
- Use math steps only for complete expressions.
- For math steps, spoken_text must explain the notation in plain English and must not include raw LaTeX markers such as $, _, ^, or commands like \\mathbb.
"""


class DeliveryStepDraft(BaseModel):
    kind: str = "text"
    display_text: str = ""
    spoken_text: str = ""
    reveal_mode: str = ""
    target: str | int | None = None


class DeliveryStepDraftBatch(BaseModel):
    steps: list[DeliveryStepDraft] = Field(default_factory=list)


@dataclass
class StepGenerationResult:
    steps: list[DeliveryStep]
    used_fallback: bool


def _format_label(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _default_reveal_mode_for_kind(kind: str) -> str:
    if kind in {"heading", "highlight"}:
        return "token"
    if kind == "pause":
        return "instant"
    if kind == "math":
        return "line"
    return "token"


def _clean_math_display_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    # Recover common JSON escape damage from unescaped LaTeX commands such as
    # \frac -> form-feed + "rac" and \begin -> backspace + "egin".
    cleaned = (
        cleaned
        .replace("\x0c", "\\f")
        .replace("\x08", "\\b")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(^|[^\\A-Za-z])rac\{", r"\1\\frac{", cleaned)
    cleaned = re.sub(r"(^|[^\\A-Za-z])mathbb\{", r"\1\\mathbb{", cleaned)
    cleaned = re.sub(r"(^|[^\\A-Za-z])egin\{", r"\1\\begin{", cleaned)

    if cleaned.startswith("$$") and cleaned.endswith("$$"):
        return cleaned
    if cleaned.startswith("$") and cleaned.endswith("$"):
        return cleaned
    return f"$${cleaned}$$"


def _fallback_section_steps(section: str, topic: str) -> list[DeliveryStep]:
    title = _format_label(section)
    return [
        DeliveryStep(
            step_id=f"{section}_step_1",
            kind="heading",
            display_text=title,
            spoken_text=f"Let's work through {title.lower()} for {topic}.",
            reveal_mode="token",
        ),
        DeliveryStep(
            step_id=f"{section}_step_2",
            kind="text",
            display_text=f"The key idea in {title.lower()} is to move one clear step at a time and keep track of what each symbol means.",
            spoken_text=f"The key idea here is to move one clear step at a time and keep track of what each symbol means.",
            reveal_mode="token",
        ),
        DeliveryStep(
            step_id=f"{section}_step_3",
            kind="text",
            display_text="We will anchor the intuition first, then connect it back to the formal statement.",
            spoken_text="We will anchor the intuition first, then connect it back to the formal statement.",
            reveal_mode="token",
        ),
    ]


def _fallback_interruption_steps(section: str, question: str) -> list[DeliveryStep]:
    return [
        DeliveryStep(
            step_id="interruption_step_1",
            kind="heading",
            display_text="Quick Clarification",
            spoken_text="Let's pause for a quick clarification.",
            reveal_mode="token",
        ),
        DeliveryStep(
            step_id="interruption_step_2",
            kind="text",
            display_text=f"Question: {question}",
            spoken_text=f"Your question is about {question}.",
            reveal_mode="token",
        ),
        DeliveryStep(
            step_id="interruption_step_3",
            kind="text",
            display_text=f"We can now connect that back to { _format_label(section).lower() } and continue from the exact point we paused.",
            spoken_text=f"That gives us the piece we needed, so we can connect it back to { _format_label(section).lower() } and continue.",
            reveal_mode="token",
        ),
    ]


def _clean_spoken_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    replacements = {
        r"\mathbb{Z}": "the integers",
        r"\mathbb{R}": "the real numbers",
        r"\mathbb{Q}": "the rational numbers",
        r"\mathbb{N}": "the natural numbers",
        r"\mathbb{C}": "the complex numbers",
        "mathbbZ": "the integers",
        "mathbbR": "the real numbers",
        "mathbbQ": "the rational numbers",
        "mathbbN": "the natural numbers",
        "mathbbC": "the complex numbers",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)

    cleaned = cleaned.replace("$$", " ")
    cleaned = re.sub(r"\$([^$]+)\$", r"\1", cleaned)
    cleaned = re.sub(r"([A-Za-z])_\{([^}]+)\}\(([^)]+)\)", r"\1 sub \2 of \3", cleaned)
    cleaned = re.sub(r"([A-Za-z])_([A-Za-z0-9]+)\(([^)]+)\)", r"\1 sub \2 of \3", cleaned)
    cleaned = re.sub(r"([A-Za-z])_\{([^}]+)\}", r"\1 sub \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])_([A-Za-z0-9]+)", r"\1 sub \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])\^\{([^}]+)\}", r"\1 to the power \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])\^([A-Za-z0-9]+)", r"\1 to the power \2", cleaned)
    cleaned = cleaned.replace("\\", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _sanitize_steps(
    raw_steps: Sequence[dict],
    *,
    section: str,
    fallback_factory: Callable[[], list[DeliveryStep]],
) -> StepGenerationResult:
    valid_kinds = {"heading", "text", "math", "highlight", "pause"}
    valid_modes = {"instant", "token", "line"}

    steps: list[DeliveryStep] = []
    for index, raw_step in enumerate(raw_steps[:6], start=1):
        if not isinstance(raw_step, dict):
            continue

        kind = str(raw_step.get("kind", "text")).strip().lower()
        if kind not in valid_kinds:
            kind = "text"

        raw_reveal_mode = raw_step.get("reveal_mode")
        reveal_mode = str(raw_reveal_mode).strip().lower() if raw_reveal_mode is not None else ""
        if reveal_mode not in valid_modes:
            reveal_mode = _default_reveal_mode_for_kind(kind)

        display_text = str(raw_step.get("display_text", "")).strip()
        spoken_text = _clean_spoken_text(str(raw_step.get("spoken_text", "")).strip())
        target = raw_step.get("target")
        target = str(target).strip() if target else None

        if kind == "math":
            display_text = _clean_math_display_text(display_text)

        if not display_text and kind != "pause":
            display_text = spoken_text
        if not spoken_text and kind not in {"highlight", "pause"}:
            spoken_text = display_text

        # Keep the board text aligned with narration for non-math content.
        # Math steps may still use a compact formula on the board with fuller speech.
        if kind in {"heading", "text"} and spoken_text:
            display_text = spoken_text

        steps.append(
            DeliveryStep(
                step_id=f"{section}_step_{index}",
                kind=kind,  # type: ignore[arg-type]
                display_text=display_text,
                spoken_text=spoken_text,
                reveal_mode=reveal_mode,  # type: ignore[arg-type]
                target=target,
            )
        )

    if len(steps) < 2:
        return StepGenerationResult(steps=fallback_factory(), used_fallback=True)

    last_visible_step_id: str | None = None
    for step in steps:
        if step.kind == "highlight":
            if step.target in {None, "", "previous"}:
                step.target = last_visible_step_id
            elif step.target and not step.target.startswith(f"{section}_step_"):
                step.target = last_visible_step_id
        elif step.kind != "pause":
            last_visible_step_id = step.step_id

    return StepGenerationResult(steps=steps, used_fallback=False)


def _merge_markers(
    steps: Sequence[DeliveryStep],
    provided_markers: Sequence[AudioMarker],
    *,
    audio_duration_ms: int,
) -> list[AudioMarker]:
    marker_map = {marker.name: marker.time_ms for marker in provided_markers}
    fallback_markers, _ = _estimate_marker_times(steps)

    merged: list[AudioMarker] = []
    last_time = 0
    for index, step in enumerate(steps):
        time_ms = marker_map.get(step.step_id, fallback_markers[index].time_ms)
        time_ms = max(time_ms, last_time)
        if index == len(steps) - 1:
            time_ms = min(time_ms, max(0, audio_duration_ms - 200))
        merged.append(AudioMarker(name=step.step_id, time_ms=time_ms))
        last_time = time_ms
    return merged


def _transcript_from_steps(steps: Sequence[DeliveryStep]) -> str:
    return "\n\n".join(step.spoken_text for step in steps if step.spoken_text)


async def _generate_steps_with_llm(
    prompt_template: str,
    variables: dict,
    *,
    section: str,
    fallback_factory: Callable[[], list[DeliveryStep]],
) -> StepGenerationResult:
    llm = get_llm("rich").with_structured_output(DeliveryStepDraftBatch, method="json_mode")
    prompt = ChatPromptTemplate.from_template(prompt_template)
    chain = prompt | llm

    last_exc: Exception | None = None
    for attempt in range(1, 3):
        try:
            result = await chain.ainvoke(variables)
            raw_steps = [step.model_dump(exclude_none=True, exclude_defaults=True) for step in result.steps]
            sanitized = _sanitize_steps(raw_steps, section=section, fallback_factory=fallback_factory)
            if sanitized.used_fallback:
                logger.warning(
                    "Structured delivery output for %s produced too few valid steps on attempt %s",
                    section,
                    attempt,
                )
                continue
            return sanitized
        except Exception as exc:  # pragma: no cover - depends on external providers
            last_exc = exc
            logger.warning(
                "Structured delivery generation failed for %s on attempt %s: %s",
                section,
                attempt,
                exc,
            )

    if last_exc is not None:
        logger.warning("Falling back to heuristic delivery steps for %s: %s", section, last_exc)
    else:
        logger.warning("Falling back to heuristic delivery steps for %s after empty structured output", section)
    return StepGenerationResult(steps=fallback_factory(), used_fallback=True)


async def _finalize_package(
    session_id: str,
    *,
    section: str,
    steps: Sequence[DeliveryStep],
    section_index: int | None = None,
    base_audio_offset_ms: int = 0,
    audio_url: str | None = None,
    audio_provider: str | None = None,
    audio_duration_ms: int | None = None,
    markers: Sequence[AudioMarker] | None = None,
) -> DeliveryPackage:
    package_id = str(uuid.uuid4())

    if audio_url is None or audio_duration_ms is None or markers is None:
        speech = await synthesize_package_audio(steps)
        await save_audio_clip(
            session_id,
            speech.clip_id,
            media_type=speech.media_type,
            audio_bytes=speech.audio_bytes,
            provider=speech.provider,
        )
        audio_url = f"/api/session/{session_id}/audio/{speech.clip_id}"
        audio_provider = speech.provider
        audio_duration_ms = speech.audio_duration_ms
        markers = speech.markers

    merged_markers = _merge_markers(steps, list(markers), audio_duration_ms=audio_duration_ms)
    package = DeliveryPackage(
        package_id=package_id,
        section=section,
        steps=list(steps),
        audio_url=audio_url,
        audio_provider=audio_provider,
        audio_duration_ms=max(1, audio_duration_ms),
        markers=merged_markers,
        transcript=_transcript_from_steps(steps),
        resume_cursor=ResumeCursor(
            package_id=package_id,
            section=section,
            step_id=steps[0].step_id if steps else None,
            audio_offset_ms=base_audio_offset_ms,
        ),
    )
    await save_delivery_package(session_id, package, section_index=section_index)
    return package


async def build_section_package(
    *,
    session_id: str,
    topic: str,
    learner_level: str,
    teaching_strategy: str,
    section: str,
    messages: Sequence[dict],
    section_index: int,
) -> DeliveryPackage:
    history = _format_conversation_history(messages)
    generated = await _generate_steps_with_llm(
        SECTION_PACKAGE_PROMPT,
        {
            "topic": topic,
            "learner_level": learner_level,
            "teaching_strategy": teaching_strategy,
            "section": section,
            "conversation_history": history,
        },
        section=section,
        fallback_factory=lambda: _fallback_section_steps(section, topic),
    )
    return await _finalize_package(
        session_id,
        section=section,
        steps=generated.steps,
        section_index=section_index if not generated.used_fallback else None,
    )


async def get_or_build_section_package(
    *,
    session_id: str,
    topic: str,
    learner_level: str,
    teaching_strategy: str,
    section: str,
    messages: Sequence[dict],
    section_index: int,
) -> DeliveryPackage:
    cached = await pop_prefetched_package(session_id, section_index)
    if cached is not None:
        return cached

    return await build_section_package(
        session_id=session_id,
        topic=topic,
        learner_level=learner_level,
        teaching_strategy=teaching_strategy,
        section=section,
        messages=messages,
        section_index=section_index,
    )


async def prefetch_section_package(
    *,
    session_id: str,
    topic: str,
    learner_level: str,
    teaching_strategy: str,
    section: str,
    messages: Sequence[dict],
    section_index: int,
) -> None:
    if await get_prefetched_package(session_id, section_index):
        return

    await build_section_package(
        session_id=session_id,
        topic=topic,
        learner_level=learner_level,
        teaching_strategy=teaching_strategy,
        section=section,
        messages=messages,
        section_index=section_index,
    )


async def build_interruption_package(
    *,
    session_id: str,
    topic: str,
    section: str,
    question: str,
) -> DeliveryPackage:
    generated = await _generate_steps_with_llm(
        INTERRUPTION_PACKAGE_PROMPT,
        {"topic": topic, "section": section, "question": question},
        section="interruption",
        fallback_factory=lambda: _fallback_interruption_steps(section, question),
    )
    return await _finalize_package(
        session_id,
        section="interruption",
        steps=generated.steps,
    )


def _select_resume_step_index(package: DeliveryPackage, cursor: ResumeCursor) -> int:
    if cursor.step_id:
        for index, step in enumerate(package.steps):
            if step.step_id == cursor.step_id:
                return index

    for index, marker in enumerate(package.markers):
        absolute_time = package.resume_cursor.audio_offset_ms + marker.time_ms
        if absolute_time >= cursor.audio_offset_ms:
            return index

    return max(0, len(package.steps) - 1)


async def build_resume_package(session_id: str, cursor: ResumeCursor) -> DeliveryPackage | None:
    original = await get_delivery_package(session_id, cursor.package_id)
    if original is None or not original.steps:
        return None

    step_index = _select_resume_step_index(original, cursor)
    selected_steps = original.steps[step_index:]
    if not selected_steps:
        return None

    marker_map = {marker.name: marker.time_ms for marker in original.markers}
    start_marker_ms = marker_map.get(selected_steps[0].step_id, 0)
    remaining_markers = [
        AudioMarker(name=marker.name, time_ms=max(0, marker.time_ms - start_marker_ms))
        for marker in original.markers
        if marker.name in {step.step_id for step in selected_steps}
    ]
    remaining_duration = max(1, original.audio_duration_ms - start_marker_ms)

    return await _finalize_package(
        session_id,
        section=original.section,
        steps=selected_steps,
        base_audio_offset_ms=original.resume_cursor.audio_offset_ms + start_marker_ms,
        audio_url=original.audio_url,
        audio_provider=original.audio_provider,
        audio_duration_ms=remaining_duration,
        markers=remaining_markers,
    )
