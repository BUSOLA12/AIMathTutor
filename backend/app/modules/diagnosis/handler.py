import asyncio
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.llm import get_llm

logger = logging.getLogger(__name__)
from app.core.structured_output import RobustJsonOutputParser, as_dict, get_float, get_string_list, get_text
from app.models.schemas import DiagnosisResult, LearnerLevel, TeachingStrategy
from app.modules.diagnosis.ml import ShadowDiagnosisOutput, run_shadow_diagnosis

LEARNER_LEVELS = {level.value for level in LearnerLevel}
TEACHING_STRATEGIES = {strategy.value for strategy in TeachingStrategy}
DIAGNOSIS_MODES = {"llm", "ml_shadow", "ml_primary"}

QUESTION_BANK_PATH = Path(__file__).parent.parent.parent.parent / "data" / "question_banks"

QUESTION_GEN_PROMPT = """You are an expert math tutor. Generate exactly 4 short diagnostic questions
to assess a student's readiness to learn the following topic.

Topic: {topic}
Subject area: {subject_area}

The questions should:
1. Probe whether the student knows the key prerequisite concepts for this topic.
2. Check for common misconceptions related to this topic.
3. Gauge the student's current comfort level (beginner → advanced).
4. Ask the student's preferred learning style (intuition, worked example, or formal definition).

Respond ONLY with a valid JSON array of 4 question strings, for example:
["Question 1?", "Question 2?", "Question 3?", "Question 4?"]"""

DIAGNOSIS_PROMPT = """You are an expert math tutor performing a student diagnosis.

Topic: {topic}
Subject area: {subject_area}
Known prerequisites for this topic: {prerequisites}

Diagnostic questions and student answers:
{qa_pairs}

Analyze the student's understanding and respond ONLY with valid JSON:
{{
  "learner_level": "beginner" | "beginner_intermediate" | "intermediate" | "advanced",
  "missing_prerequisites": ["list of missing prerequisite concepts"],
  "misconception_labels": ["wrong_implication" | "definition_confusion" | "notation_confusion" | "intuition_gap" | "proof_step_gap" | "overgeneralization" | "quantifier_confusion"],
  "recommended_teaching_strategy": "intuition_first" | "example_first" | "formal_definition_first" | "proof_first" | "prerequisite_micro_lesson_first",
  "diagnostic_confidence": 0.0 to 1.0
}}"""


@lru_cache(maxsize=8)
def _load_question_bank(subject_area: str) -> dict:
    path = QUESTION_BANK_PATH / f"{subject_area}.json"
    if not path.exists():
        path = QUESTION_BANK_PATH / "real_analysis.json"
    with open(path) as f:
        return json.load(f)


def _try_static_questions(topic: str, subject_area: str) -> list[str] | None:
    """Fast-path: return pre-written questions if the topic is in the bank."""
    bank = _load_question_bank(subject_area)
    topic_key = topic.lower().replace(" ", "_")
    questions = bank.get("topic_questions", {}).get(topic_key)
    if questions:
        return questions[:4]
    return None


@dataclass(frozen=True)
class DiagnosticQuestionBatchPayload:
    questions: list[str]
    source: str


async def generate_diagnostic_question_batch(
    topic: str,
    subject_area: str,
    prerequisites: list[str],
) -> DiagnosticQuestionBatchPayload:
    """Return the delivered diagnosis questions together with their source."""
    static = _try_static_questions(topic, subject_area)
    if static:
        return DiagnosticQuestionBatchPayload(questions=static, source="question_bank")

    llm = get_llm("fast")
    prompt = ChatPromptTemplate.from_template(QUESTION_GEN_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    try:
        result = await chain.ainvoke({"topic": topic, "subject_area": subject_area})
        if isinstance(result, list) and len(result) >= 2:
            return DiagnosticQuestionBatchPayload(
                questions=[str(q) for q in result[:4]],
                source="llm_generated",
            )
    except Exception:
        logger.warning("LLM question generation failed for topic %r, falling back to generic questions", topic, exc_info=True)

    return DiagnosticQuestionBatchPayload(
        questions=[
            f"What do you already know about {topic}?",
            f"Can you describe any concepts that are prerequisites for {topic}?",
            f"What part of {topic} do you find most confusing or unfamiliar?",
            "Would you prefer to start with intuition, a worked example, or the formal definition?",
        ],
        source="generic_fallback",
    )


async def get_diagnostic_questions(topic: str, subject_area: str, prerequisites: list[str]) -> list[str]:
    """Generate 4 targeted diagnostic questions for the given topic using the LLM."""
    batch = await generate_diagnostic_question_batch(topic, subject_area, prerequisites)
    return batch.questions


async def run_diagnosis(
    session_id: str,
    topic: str,
    subject_area: str,
    prerequisites: list[str],
    questions: list[str],
    answers: list[str],
) -> DiagnosisResult:
    result = await _invoke_llm_diagnosis(
        topic=topic,
        subject_area=subject_area,
        prerequisites=prerequisites,
        questions=questions,
        answers=answers,
    )
    return _coerce_diagnosis_result(session_id, result)


def get_diagnosis_mode() -> str:
    mode = str(settings.diagnosis_mode or "ml_shadow").strip().lower()
    return mode if mode in DIAGNOSIS_MODES else "ml_shadow"


async def run_diagnosis_with_shadow(
    *,
    session_id: str,
    topic: str,
    subject_area: str,
    prerequisites: list[str],
    questions: list[str],
    answers: list[str],
    response_times_sec: list[float] | None = None,
    confidence_self_report: str | None = None,
) -> tuple[DiagnosisResult, str, ShadowDiagnosisOutput]:
    mode = get_diagnosis_mode()
    if mode == "llm":
        live_result = await run_diagnosis(
            session_id=session_id,
            topic=topic,
            subject_area=subject_area,
            prerequisites=prerequisites,
            questions=questions,
            answers=answers,
        )
        return live_result, "llm_fast", ShadowDiagnosisOutput(
            source=None,
            status="disabled",
            prediction=None,
            confidence=None,
        )

    live_result, shadow = await asyncio.gather(
        run_diagnosis(
            session_id=session_id,
            topic=topic,
            subject_area=subject_area,
            prerequisites=prerequisites,
            questions=questions,
            answers=answers,
        ),
        run_shadow_diagnosis(
            session_id=session_id,
            topic=topic,
            subject_area=subject_area,
            questions=questions,
            answers=answers,
            response_times_sec=response_times_sec,
            confidence_self_report=confidence_self_report,
        ),
    )

    if (
        mode == "ml_primary"
        and shadow.status == "ready"
        and shadow.prediction
        and float(shadow.confidence or 0.0) >= float(settings.diagnosis_ml_primary_min_confidence)
    ):
        return (
            _coerce_diagnosis_result(session_id, shadow.prediction),
            str(shadow.source or "sklearn_text_baseline"),
            shadow,
        )

    return live_result, "llm_fast", shadow


async def _invoke_llm_diagnosis(
    *,
    topic: str,
    subject_area: str,
    prerequisites: list[str],
    questions: list[str],
    answers: list[str],
) -> dict:
    llm = get_llm("fast")
    prompt = ChatPromptTemplate.from_template(DIAGNOSIS_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    qa_pairs = "\n".join(
        f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(zip(questions, answers))
    )

    return as_dict(await chain.ainvoke({
        "topic": topic,
        "subject_area": subject_area,
        "prerequisites": ", ".join(prerequisites) or "none specified",
        "qa_pairs": qa_pairs,
    }))


def _coerce_diagnosis_result(session_id: str, result: dict) -> DiagnosisResult:
    return DiagnosisResult(
        session_id=session_id,
        learner_level=get_text(
            result,
            "learner_level",
            LearnerLevel.beginner_intermediate.value,
            allowed=LEARNER_LEVELS,
        ),
        missing_prerequisites=get_string_list(result, "missing_prerequisites"),
        misconception_labels=get_string_list(result, "misconception_labels"),
        recommended_teaching_strategy=get_text(
            result,
            "recommended_teaching_strategy",
            TeachingStrategy.intuition_first.value,
            allowed=TEACHING_STRATEGIES,
        ),
        diagnostic_confidence=get_float(result, "diagnostic_confidence", 0.7, minimum=0.0, maximum=1.0),
    )
