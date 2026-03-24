import json
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.diagnosis.store import list_overlay_templates


ROOT_DIR = Path(__file__).resolve().parents[3]


def _taxonomy_dir() -> Path:
    configured = Path(settings.diagnosis_taxonomy_dir)
    if configured.is_absolute():
        return configured
    return ROOT_DIR / configured


def normalize_topic_key(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(topic or "").strip().lower()).strip("_")


def normalize_question_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower()).strip()


@dataclass(frozen=True)
class CanonicalQuestionMatch:
    template_id: str
    topic_key: str
    topic_family: str
    question_role: str
    question_text: str
    skills: dict[str, float]
    misconception_probes: dict[str, float]
    reference_answers: tuple[str, ...]
    score: float
    template_source: str = "file"


@lru_cache(maxsize=64)
def _iter_file_templates(subject_area: str, topic_key: str) -> list[dict]:
    taxonomy = load_diagnosis_taxonomy(subject_area)
    topics = taxonomy.get("topics", {})
    templates: list[dict] = []

    for section_name in ("general_questions", "misconception_probe_questions"):
        for template in taxonomy.get(section_name, []):
            templates.append(
                {
                    **template,
                    "topic_key": template.get("topic_key", "general"),
                    "topic_family": template.get("topic_family", "general"),
                }
            )

    topic_entry = topics.get(topic_key) or {}
    for template in topic_entry.get("question_templates", []):
        templates.append(
            {
                **template,
                "topic_key": topic_key,
                "topic_family": topic_entry.get("family", "general"),
            }
        )

    return templates


@lru_cache(maxsize=8)
def load_diagnosis_taxonomy(subject_area: str) -> dict:
    path = _taxonomy_dir() / f"{subject_area}.json"
    if not path.exists():
        path = _taxonomy_dir() / "real_analysis.json"
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_coverage(coverage: dict[str, float]) -> dict[str, float]:
    max_value = max(coverage.values(), default=0.0)
    if max_value > 0:
        return {key: round(value / max_value, 4) for key, value in coverage.items()}
    return coverage


def _match_from_template(template: dict, *, topic_key: str, score: float) -> CanonicalQuestionMatch:
    return CanonicalQuestionMatch(
        template_id=str(template.get("template_id", "")),
        topic_key=str(template.get("topic_key", topic_key)),
        topic_family=str(template.get("topic_family", "general")),
        question_role=str(template.get("question_role", "concept_check")),
        question_text=str(template.get("text", "")),
        skills={str(key): float(value) for key, value in dict(template.get("skills", {})).items()},
        misconception_probes={
            str(key): float(value)
            for key, value in dict(template.get("misconception_probes", {})).items()
        },
        reference_answers=tuple(str(item) for item in template.get("reference_answers", [])),
        score=score,
        template_source=str(template.get("template_source", "file")),
    )


def _canonicalize_from_templates(
    templates: list[dict],
    *,
    topic_key: str,
    question_text: str,
    minimum_score: float = 0.72,
) -> CanonicalQuestionMatch | None:
    normalized_question = normalize_question_text(question_text)
    if not normalized_question:
        return None

    best: CanonicalQuestionMatch | None = None
    for template in templates:
        candidates = [template.get("text", "")]
        candidates.extend(template.get("aliases", []))
        for candidate in candidates:
            normalized_candidate = normalize_question_text(candidate)
            if not normalized_candidate:
                continue
            score = SequenceMatcher(None, normalized_question, normalized_candidate).ratio()
            if normalized_question == normalized_candidate:
                score = 1.0
            if best is None or score > best.score:
                best = _match_from_template(template, topic_key=topic_key, score=score)

    if best and best.score >= minimum_score:
        return best
    return None


def canonicalize_question(subject_area: str, topic: str, question_text: str) -> CanonicalQuestionMatch | None:
    topic_key = normalize_topic_key(topic)
    return _canonicalize_from_templates(
        _iter_file_templates(subject_area, topic_key),
        topic_key=topic_key,
        question_text=question_text,
    )


def canonicalize_questions(subject_area: str, topic: str, questions: list[str]) -> list[CanonicalQuestionMatch | None]:
    return [canonicalize_question(subject_area, topic, question) for question in questions]


def _overlay_template_to_dict(template, aliases: list[str]) -> dict:
    return {
        "template_id": str(template.template_id),
        "topic_key": str(template.topic_key),
        "topic_family": str(template.topic_family or "general"),
        "question_role": str(template.question_role or "concept_check"),
        "text": str(template.text or ""),
        "aliases": list(aliases),
        "skills": dict(template.skills or {}),
        "misconception_probes": dict(template.misconception_probes or {}),
        "reference_answers": list(template.reference_answers or []),
        "template_source": "overlay",
    }


async def _iter_templates_with_overlay(db: AsyncSession, subject_area: str, topic_key: str) -> list[dict]:
    overlay_templates = [
        _overlay_template_to_dict(template, aliases)
        for template, aliases in await list_overlay_templates(
            db,
            subject_area=subject_area,
            topic_key=topic_key,
        )
    ]
    return overlay_templates + _iter_file_templates(subject_area, topic_key)


async def canonicalize_question_with_overlay(
    db: AsyncSession,
    subject_area: str,
    topic: str,
    question_text: str,
) -> CanonicalQuestionMatch | None:
    topic_key = normalize_topic_key(topic)
    templates = await _iter_templates_with_overlay(db, subject_area, topic_key)
    return _canonicalize_from_templates(
        templates,
        topic_key=topic_key,
        question_text=question_text,
    )


async def canonicalize_questions_with_overlay(
    db: AsyncSession,
    subject_area: str,
    topic: str,
    questions: list[str],
) -> list[CanonicalQuestionMatch | None]:
    topic_key = normalize_topic_key(topic)
    templates = await _iter_templates_with_overlay(db, subject_area, topic_key)
    return [
        _canonicalize_from_templates(templates, topic_key=topic_key, question_text=question)
        for question in questions
    ]


def find_best_question_match(subject_area: str, topic: str, question_text: str) -> CanonicalQuestionMatch | None:
    topic_key = normalize_topic_key(topic)
    return _canonicalize_from_templates(
        _iter_file_templates(subject_area, topic_key),
        topic_key=topic_key,
        question_text=question_text,
        minimum_score=0.0,
    )


async def find_best_question_match_with_overlay(
    db: AsyncSession,
    subject_area: str,
    topic: str,
    question_text: str,
) -> CanonicalQuestionMatch | None:
    topic_key = normalize_topic_key(topic)
    templates = await _iter_templates_with_overlay(db, subject_area, topic_key)
    return _canonicalize_from_templates(
        templates,
        topic_key=topic_key,
        question_text=question_text,
        minimum_score=0.0,
    )


def build_probe_features_from_matches(matches: list[CanonicalQuestionMatch | None]) -> dict[str, float]:
    coverage: dict[str, float] = {}
    for match in matches:
        if match is None:
            continue
        for skill, weight in match.skills.items():
            coverage[skill] = coverage.get(skill, 0.0) + float(weight)
        for misconception, weight in match.misconception_probes.items():
            key = f"misconception::{misconception}"
            coverage[key] = coverage.get(key, 0.0) + float(weight)
    return _normalize_coverage(coverage)


def build_q_matrix(subject_area: str, topic: str, canonical_question_ids: list[str]) -> dict[str, float]:
    question_index = {
        str(t.get("template_id", "")): t
        for t in _iter_file_templates(subject_area, normalize_topic_key(topic))
    }
    coverage: dict[str, float] = {}
    for question_id in canonical_question_ids:
        template = question_index.get(str(question_id))
        if not template:
            continue
        for skill, weight in dict(template.get("skills", {})).items():
            coverage[skill] = coverage.get(skill, 0.0) + float(weight)
        for misconception, weight in dict(template.get("misconception_probes", {})).items():
            key = f"misconception::{misconception}"
            coverage[key] = coverage.get(key, 0.0) + float(weight)
    return _normalize_coverage(coverage)


def build_probe_features(subject_area: str, topic: str, canonical_matches: list[CanonicalQuestionMatch | None]) -> dict[str, float]:
    question_ids = [match.template_id for match in canonical_matches if match and match.template_source == "file"]
    if any(m for m in canonical_matches if m and m.template_source != "file"):
        return build_probe_features_from_matches(canonical_matches)
    return build_q_matrix(subject_area, topic, question_ids)


def estimate_reference_similarity(answer: str, reference_answers: tuple[str, ...]) -> float:
    normalized_answer = normalize_question_text(answer)
    if not normalized_answer or not reference_answers:
        return 0.0
    return round(
        max(
            SequenceMatcher(None, normalized_answer, normalize_question_text(reference)).ratio()
            for reference in reference_answers
        ),
        4,
    )


def summarize_confidence_text(text: str | None) -> str:
    normalized = normalize_question_text(text or "")
    if not normalized:
        return "unknown"
    if any(word in normalized for word in ("high", "very", "confident", "sure")):
        return "high"
    if any(word in normalized for word in ("low", "not", "unsure", "guess")):
        return "low"
    return "medium"


def response_time_bucket(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 8:
        return "fast"
    if seconds < 25:
        return "medium"
    if math.isfinite(seconds):
        return "slow"
    return "unknown"
