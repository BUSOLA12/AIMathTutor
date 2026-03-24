import asyncio
from dataclasses import dataclass
from hashlib import sha1

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.modules.diagnosis.dataset import build_training_record_from_matches
from app.modules.diagnosis.store import (
    create_background_job,
    create_overlay_template,
    get_background_job,
    get_background_job_by_dedupe_key,
    get_canonicalization_audits,
    get_diagnosis_run,
    get_diagnostic_responses_for_run,
    get_question_batch,
    list_recoverable_background_jobs,
    mark_diagnosis_run_materialization_status,
    save_materialized_record,
    update_question_batch_canonicalization,
    upsert_canonicalization_audit,
    utc_now,
)
from app.modules.diagnosis.taxonomy import (
    build_probe_features_from_matches,
    canonicalize_questions_with_overlay,
    find_best_question_match_with_overlay,
    load_diagnosis_taxonomy,
    normalize_question_text,
    normalize_topic_key,
)
from app.session.manager import get_redis

JOB_TYPE_GENERATED_ANALYSIS = "generated_question_analysis"
JOB_TYPE_TRAINING_MATERIALIZATION = "diagnosis_training_materialization"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
MATCHED_EXISTING = "matched_existing"
AUTO_PROMOTED = "auto_promoted"
REVIEW_PENDING = "review_pending"
UNRESOLVED = "unresolved"


class RetryableDiagnosisJobError(RuntimeError):
    pass


@dataclass
class InferredTemplate:
    question_role: str
    topic_family: str
    skills: dict[str, float]
    misconception_probes: dict[str, float]
    reference_answers: list[str]
    confidence: float


def _job_dedupe_key(job_type: str, *, question_batch_id: int | None, diagnosis_run_id: int | None) -> str:
    if question_batch_id is not None:
        return f"{job_type}:batch:{question_batch_id}"
    if diagnosis_run_id is not None:
        return f"{job_type}:run:{diagnosis_run_id}"
    raise ValueError("A background job needs a question batch id or diagnosis run id.")


async def _push_job_id(job_id: int) -> None:
    redis = await get_redis()
    await redis.rpush(settings.diagnosis_background_queue_key, str(job_id))


async def enqueue_diagnosis_background_job(
    db: AsyncSession,
    *,
    job_type: str,
    session_id: str | None,
    question_batch_id: int | None = None,
    diagnosis_run_id: int | None = None,
    payload: dict | None = None,
) -> tuple[object, bool]:
    dedupe_key = _job_dedupe_key(
        job_type,
        question_batch_id=question_batch_id,
        diagnosis_run_id=diagnosis_run_id,
    )
    job = await get_background_job_by_dedupe_key(db, dedupe_key)
    created = False

    if job is None:
        job = await create_background_job(
            db,
            job_type=job_type,
            dedupe_key=dedupe_key,
            session_id=session_id,
            question_batch_id=question_batch_id,
            diagnosis_run_id=diagnosis_run_id,
            payload=payload or {},
            max_attempts=settings.diagnosis_background_retry_limit,
        )
        created = True
    elif job.status == JOB_STATUS_FAILED:
        job.status = JOB_STATUS_QUEUED
        job.last_error = None
        job.finished_at = None
        job.started_at = None
        job.payload = dict(payload or job.payload or {})
        await db.flush()

    await db.commit()
    if job.status == JOB_STATUS_QUEUED:
        await _push_job_id(job.id)
    return job, created


def _infer_topic_family(subject_area: str, topic: str, question_text: str) -> str:
    topic_key = normalize_topic_key(topic)
    taxonomy = load_diagnosis_taxonomy(subject_area)
    topic_entry = dict(taxonomy.get("topics", {})).get(topic_key)
    if topic_entry:
        return str(topic_entry.get("family", "general"))

    normalized = f"{topic_key} {normalize_question_text(question_text)}"
    if any(token in normalized for token in ("sequence", "cauchy", "subsequence", "bounded", "convergen")):
        return "sequences"
    if any(token in normalized for token in ("continuity", "continuous", "uniform", "function", "epsilon", "delta", "limit")):
        return "continuity"
    return "general"


def _infer_skills(question_text: str) -> dict[str, float]:
    normalized = normalize_question_text(question_text)
    skills: dict[str, float] = {}

    if "sequence" in normalized:
        skills["sequence_basics"] = max(skills.get("sequence_basics", 0.0), 0.6)
    if "subsequence" in normalized:
        skills["subsequence"] = 1.0
    if "bounded" in normalized:
        skills["boundedness"] = 1.0
    if any(token in normalized for token in ("converg", "limit")):
        skills["convergence"] = max(skills.get("convergence", 0.0), 0.8)
    if "continuity" in normalized or "continuous" in normalized:
        skills["continuity"] = max(skills.get("continuity", 0.0), 0.8)
    if "uniform continuity" in normalized or "uniformly continuous" in normalized:
        skills["uniform_continuity"] = 1.0
        skills["quantifier_reasoning"] = max(skills.get("quantifier_reasoning", 0.0), 0.6)
    if "epsilon" in normalized or "delta" in normalized:
        skills["epsilon_delta_reasoning"] = 1.0
        skills["quantifier_reasoning"] = max(skills.get("quantifier_reasoning", 0.0), 0.8)
    if "quantifier" in normalized or "for every" in normalized or "there exists" in normalized or "pointwise" in normalized:
        skills["quantifier_reasoning"] = max(skills.get("quantifier_reasoning", 0.0), 0.8)
    if "cauchy" in normalized:
        skills["cauchy_definition"] = 1.0
    if "proof" in normalized:
        skills["proof_logic"] = 0.8
    if "set" in normalized:
        skills["set_language"] = 0.7
    if "function" in normalized:
        skills["function_basics"] = max(skills.get("function_basics", 0.0), 0.5)
    if "notation" in normalized or any(symbol in question_text for symbol in ("_", "^", "\\", "f(")):
        skills["notation"] = max(skills.get("notation", 0.0), 0.6)
    return skills


def _infer_misconception_probes(question_text: str, question_role: str) -> dict[str, float]:
    normalized = normalize_question_text(question_text)
    probes: dict[str, float] = {}

    if question_role in {"definition_probe", "concept_check"}:
        probes["definition_confusion"] = 0.8
    if "pointwise" in normalized or "uniform continuity" in normalized or "epsilon" in normalized or "delta" in normalized:
        probes["quantifier_confusion"] = max(probes.get("quantifier_confusion", 0.0), 0.8)
    if question_role in {"misconception_probe", "reasoning_probe"} or "true or false" in normalized:
        probes["wrong_implication"] = max(probes.get("wrong_implication", 0.0), 0.8)
        probes["overgeneralization"] = max(probes.get("overgeneralization", 0.0), 0.6)
    if question_role == "example_probe":
        probes["intuition_gap"] = max(probes.get("intuition_gap", 0.0), 0.5)
        probes["overgeneralization"] = max(probes.get("overgeneralization", 0.0), 0.7)
    if "notation" in normalized:
        probes["notation_confusion"] = max(probes.get("notation_confusion", 0.0), 0.7)
    return probes


def _infer_question_role(question_text: str) -> tuple[str, float]:
    normalized = normalize_question_text(question_text)
    if any(phrase in normalized for phrase in ("would you prefer", "would you like", "prefer to start")):
        return "preference", 0.98
    if normalized.startswith("true or false"):
        return "misconception_probe", 0.93
    if "give an example" in normalized or normalized.startswith("can you give an example"):
        return "example_probe", 0.9
    if "difference between" in normalized:
        return "concept_check", 0.88
    if "definition" in normalized or normalized.startswith("what is a ") or normalized.startswith("what is the definition") or normalized.startswith("what does it mean"):
        return "definition_probe", 0.92
    if "why or why not" in normalized or normalized.startswith("do you think"):
        return "reasoning_probe", 0.82
    return "concept_check", 0.7


def infer_generated_template(subject_area: str, topic: str, question_text: str) -> InferredTemplate:
    question_role, confidence = _infer_question_role(question_text)
    topic_family = _infer_topic_family(subject_area, topic, question_text)
    skills = _infer_skills(question_text)
    misconception_probes = _infer_misconception_probes(question_text, question_role)

    if question_role == "preference":
        reference_answers = [
            "Intuition first.",
            "A worked example first.",
            "Formal definition first.",
        ]
    elif question_role == "definition_probe":
        reference_answers = [f"A correct answer should define the concept asked in: {question_text}"]
    elif question_role == "example_probe":
        reference_answers = [f"A correct answer should provide a valid example for: {question_text}"]
    else:
        reference_answers = [f"A correct answer should address: {question_text}"]

    if question_role != "preference" and not skills:
        confidence = min(confidence, 0.68)
    return InferredTemplate(
        question_role=question_role,
        topic_family=topic_family,
        skills=skills,
        misconception_probes=misconception_probes,
        reference_answers=reference_answers,
        confidence=round(confidence, 4),
    )


def build_overlay_template_id(subject_area: str, topic_key: str, question_text: str) -> str:
    digest = sha1(f"{subject_area}:{topic_key}:{normalize_question_text(question_text)}".encode("utf-8")).hexdigest()
    return f"overlay.{topic_key or 'general'}.{digest[:12]}"


async def _process_generated_question_analysis(db: AsyncSession, question_batch_id: int) -> None:
    batch = await get_question_batch(db, question_batch_id)
    if batch is None:
        return

    batch.canonicalization_status = "running"
    await db.flush()

    canonical_ids: list[str | None] = []
    canonical_sources: list[str | None] = []
    canonical_scores: list[float | None] = []
    unresolved_count = 0

    for index, question_text in enumerate(list(batch.questions or [])):
        best_match = await find_best_question_match_with_overlay(
            db,
            batch.subject_area,
            batch.topic,
            question_text,
        )

        if best_match is not None and best_match.score >= settings.diagnosis_overlay_review_threshold:
            canonical_ids.append(best_match.template_id)
            canonical_sources.append(best_match.template_source)
            canonical_scores.append(round(best_match.score, 4))
            await upsert_canonicalization_audit(
                db,
                question_batch_id=batch.id,
                question_index=index,
                question_text=question_text,
                matched_template_id=best_match.template_id,
                match_source=best_match.template_source,
                similarity_score=round(best_match.score, 4),
                inferred_question_role=best_match.question_role,
                inferred_skills=best_match.skills,
                inferred_misconception_probes=best_match.misconception_probes,
                promotion_decision=MATCHED_EXISTING,
                promotion_confidence=round(best_match.score, 4),
                overlay_template_id=None,
            )
            continue

        inferred = infer_generated_template(batch.subject_area, batch.topic, question_text)
        promotion_decision = UNRESOLVED
        overlay_template_id = None
        canonical_id = None
        canonical_source = None
        canonical_score = round(best_match.score, 4) if best_match is not None else None

        if inferred.confidence >= settings.diagnosis_overlay_auto_promote_threshold:
            promo_mode, active_flag, promotion_decision = "auto", True, AUTO_PROMOTED
        elif inferred.confidence >= settings.diagnosis_overlay_review_threshold:
            promo_mode, active_flag, promotion_decision = "review_pending", False, REVIEW_PENDING
        else:
            promo_mode = None

        if promo_mode is not None:
            template = await create_overlay_template(
                db,
                template_id=build_overlay_template_id(batch.subject_area, batch.topic_key, question_text),
                subject_area=batch.subject_area,
                topic_key=batch.topic_key,
                topic_family=inferred.topic_family,
                question_role=inferred.question_role,
                text=question_text,
                aliases=[],
                skills=inferred.skills,
                misconception_probes=inferred.misconception_probes,
                reference_answers=inferred.reference_answers,
                promotion_confidence=inferred.confidence,
                promotion_mode=promo_mode,
                active=active_flag,
                source_question_batch_id=batch.id,
                source_question_index=index,
                source_question_text=question_text,
            )
            overlay_template_id = template.id
            if promotion_decision == AUTO_PROMOTED:
                canonical_id = template.template_id
                canonical_source = "overlay"
                canonical_score = inferred.confidence
        else:
            unresolved_count += 1

        canonical_ids.append(canonical_id)
        canonical_sources.append(canonical_source)
        canonical_scores.append(canonical_score)
        await upsert_canonicalization_audit(
            db,
            question_batch_id=batch.id,
            question_index=index,
            question_text=question_text,
            matched_template_id=canonical_id,
            match_source=canonical_source,
            similarity_score=canonical_score,
            inferred_question_role=inferred.question_role,
            inferred_skills=inferred.skills,
            inferred_misconception_probes=inferred.misconception_probes,
            promotion_decision=promotion_decision,
            promotion_confidence=inferred.confidence,
            overlay_template_id=overlay_template_id,
        )

    final_status = "completed"
    if unresolved_count and any(canonical_ids):
        final_status = "partial"
    elif unresolved_count and not any(canonical_ids):
        final_status = "unresolved"

    await update_question_batch_canonicalization(
        db,
        batch=batch,
        canonicalization_status=final_status,
        canonical_question_ids=canonical_ids,
        canonical_sources=canonical_sources,
        canonical_scores=canonical_scores,
    )


async def _process_training_materialization(db: AsyncSession, diagnosis_run_id: int) -> None:
    run = await get_diagnosis_run(db, diagnosis_run_id)
    if run is None:
        return

    batch = await get_question_batch(db, run.question_batch_id)
    if batch is not None and batch.source == "llm_generated" and batch.canonicalization_status in {"pending", "running"}:
        raise RetryableDiagnosisJobError("Waiting for generated question analysis to finish.")

    responses = await get_diagnostic_responses_for_run(db, diagnosis_run_id)
    questions = [response.question or "" for response in responses]
    answers = [response.answer or "" for response in responses]
    response_times = [response.response_time_sec for response in responses]

    matches = await canonicalize_questions_with_overlay(
        db,
        run.subject_area,
        run.topic,
        questions,
    )
    canonical_question_ids = [match.template_id if match else None for match in matches]
    canonical_sources = [match.template_source if match else None for match in matches]
    canonical_confidences = [round(match.score, 4) if match else None for match in matches]
    unresolved_indices = [index for index, question_id in enumerate(canonical_question_ids) if not question_id]

    payload = build_training_record_from_matches(
        {
            "session_id": run.session_id,
            "subject_area": run.subject_area,
            "topic": run.topic,
            "questions": questions,
            "answers": answers,
            "response_times_sec": response_times,
            "confidence_self_report": run.confidence_self_report,
            "labels": {
                "learner_level": dict(run.live_result or {}).get("learner_level"),
                "missing_prerequisites": list(dict(run.live_result or {}).get("missing_prerequisites") or []),
                "misconception_labels": list(dict(run.live_result or {}).get("misconception_labels") or []),
                "recommended_teaching_strategy": dict(run.live_result or {}).get("recommended_teaching_strategy"),
            },
        },
        matches=matches,
        canonical_question_ids=canonical_question_ids,
        canonical_sources=canonical_sources,
        canonical_confidences=canonical_confidences,
    )
    payload["probe_features"] = build_probe_features_from_matches(matches)
    payload["materialized_from_run_id"] = diagnosis_run_id
    payload["question_batch_id"] = run.question_batch_id

    await save_materialized_record(
        db,
        diagnosis_run_id=diagnosis_run_id,
        question_batch_id=run.question_batch_id,
        session_id=run.session_id,
        subject_area=run.subject_area,
        topic=run.topic,
        canonical_question_ids=canonical_question_ids,
        canonical_sources=canonical_sources,
        canonical_confidences=canonical_confidences,
        unresolved_question_indices=unresolved_indices,
        payload=payload,
    )


async def _handle_job_error(job_id: int, error: Exception) -> None:
    async with AsyncSessionLocal() as db:
        job = await get_background_job(db, job_id)
        if job is None:
            return
        if int(job.attempts or 0) < int(job.max_attempts or settings.diagnosis_background_retry_limit):
            job.status = JOB_STATUS_QUEUED
            job.last_error = str(error)
            await db.commit()
            await _push_job_id(job.id)
        else:
            job.status = JOB_STATUS_FAILED
            job.finished_at = utc_now()
            job.last_error = str(error)
            if job.diagnosis_run_id:
                await mark_diagnosis_run_materialization_status(db, job.diagnosis_run_id, "failed")
            await db.commit()


async def process_diagnosis_background_job(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await get_background_job(db, job_id)
        if job is None or job.status == JOB_STATUS_COMPLETED:
            return

        job.status = JOB_STATUS_RUNNING
        job.started_at = utc_now()
        job.attempts = int(job.attempts or 0) + 1
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            job = await get_background_job(db, job_id)
            if job is None:
                return

            if job.job_type == JOB_TYPE_GENERATED_ANALYSIS:
                await _process_generated_question_analysis(db, int(job.question_batch_id or 0))
            elif job.job_type == JOB_TYPE_TRAINING_MATERIALIZATION:
                await _process_training_materialization(db, int(job.diagnosis_run_id or 0))
            else:
                raise RuntimeError(f"Unknown background job type: {job.job_type}")

            job.status = JOB_STATUS_COMPLETED
            job.finished_at = utc_now()
            job.last_error = None
            await db.commit()
    except RetryableDiagnosisJobError as error:
        await _handle_job_error(job_id, error)
    except Exception as error:  # pragma: no cover - defensive worker guard
        await _handle_job_error(job_id, error)


async def recover_diagnosis_background_jobs() -> None:
    async with AsyncSessionLocal() as db:
        jobs = await list_recoverable_background_jobs(db)

    stale_after = max(30, int(settings.diagnosis_background_stale_after_sec))
    now = utc_now()
    for job in jobs:
        if job.status == JOB_STATUS_QUEUED:
            await _push_job_id(job.id)
            continue
        if job.status == JOB_STATUS_RUNNING and job.started_at is not None:
            if (now - job.started_at).total_seconds() >= stale_after:
                async with AsyncSessionLocal() as db:
                    stale_job = await get_background_job(db, job.id)
                    if stale_job is None:
                        continue
                    stale_job.status = JOB_STATUS_QUEUED
                    stale_job.last_error = "Recovered stale running job."
                    await db.commit()
                await _push_job_id(job.id)


async def run_diagnosis_worker_forever() -> None:
    await recover_diagnosis_background_jobs()
    redis = await get_redis()
    queue_key = settings.diagnosis_background_queue_key

    while True:
        message = await redis.blpop(queue_key, timeout=5)
        if message is None:
            continue

        _, raw_job_id = message
        try:
            job_id = int(raw_job_id)
        except (TypeError, ValueError):
            continue
        await process_diagnosis_background_job(job_id)
