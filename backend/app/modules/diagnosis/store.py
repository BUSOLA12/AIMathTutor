from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import DiagnosisResult
from app.models.tables import (
    DiagnosisBackgroundJob,
    DiagnosisCanonicalizationAudit,
    DiagnosisMaterializedRecord,
    DiagnosisOverlayAlias,
    DiagnosisOverlayTemplate,
    DiagnosisQuestionBatch,
    DiagnosisRun,
    DiagnosticResponse,
    Session as SessionTable,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_question_batch(
    db: AsyncSession,
    *,
    session_id: str,
    topic: str,
    topic_key: str,
    subject_area: str,
    source: str,
    questions: list[str],
    canonicalization_status: str = "pending",
    canonical_question_ids: list[str | None] | None = None,
    canonical_sources: list[str | None] | None = None,
    canonical_scores: list[float | None] | None = None,
) -> DiagnosisQuestionBatch:
    batch = DiagnosisQuestionBatch(
        session_id=session_id,
        topic=topic,
        topic_key=topic_key,
        subject_area=subject_area,
        source=source,
        status="issued",
        questions=list(questions),
        question_count=len(questions),
        canonicalization_status=canonicalization_status,
        canonical_question_ids=list(canonical_question_ids or []),
        canonical_sources=list(canonical_sources or []),
        canonical_scores=list(canonical_scores or []),
    )
    db.add(batch)
    await db.flush()
    return batch


async def get_question_batch(db: AsyncSession, batch_id: int | None) -> DiagnosisQuestionBatch | None:
    if batch_id is None:
        return None
    return await db.scalar(select(DiagnosisQuestionBatch).where(DiagnosisQuestionBatch.id == batch_id))


async def get_latest_issued_question_batch(db: AsyncSession, session_id: str) -> DiagnosisQuestionBatch | None:
    return await db.scalar(
        select(DiagnosisQuestionBatch)
        .where(
            DiagnosisQuestionBatch.session_id == session_id,
            DiagnosisQuestionBatch.status == "issued",
        )
        .order_by(desc(DiagnosisQuestionBatch.id))
    )


async def get_latest_question_batch(db: AsyncSession, session_id: str) -> DiagnosisQuestionBatch | None:
    return await db.scalar(
        select(DiagnosisQuestionBatch)
        .where(DiagnosisQuestionBatch.session_id == session_id)
        .order_by(desc(DiagnosisQuestionBatch.id))
    )


async def mark_question_batch_submitted(db: AsyncSession, batch: DiagnosisQuestionBatch | None) -> None:
    if batch is None:
        return
    batch.status = "submitted"
    batch.submitted_at = utc_now()


async def update_question_batch_canonicalization(
    db: AsyncSession,
    *,
    batch: DiagnosisQuestionBatch,
    canonicalization_status: str,
    canonical_question_ids: list[str | None],
    canonical_sources: list[str | None],
    canonical_scores: list[float | None],
) -> DiagnosisQuestionBatch:
    batch.canonicalization_status = canonicalization_status
    batch.canonical_question_ids = list(canonical_question_ids)
    batch.canonical_sources = list(canonical_sources)
    batch.canonical_scores = list(canonical_scores)
    await db.flush()
    return batch


async def list_overlay_templates(
    db: AsyncSession,
    *,
    subject_area: str,
    topic_key: str,
    include_inactive: bool = False,
) -> list[tuple[DiagnosisOverlayTemplate, list[str]]]:
    query = (
        select(DiagnosisOverlayTemplate)
        .where(
            DiagnosisOverlayTemplate.subject_area == subject_area,
            DiagnosisOverlayTemplate.topic_key.in_([topic_key, "general"]),
        )
        .order_by(DiagnosisOverlayTemplate.id.asc())
    )
    if not include_inactive:
        query = query.where(DiagnosisOverlayTemplate.active.is_(True))

    templates = list((await db.execute(query)).scalars().all())
    if not templates:
        return []

    aliases = list(
        (
            await db.execute(
                select(DiagnosisOverlayAlias)
                .where(DiagnosisOverlayAlias.overlay_template_id.in_([template.id for template in templates]))
                .order_by(DiagnosisOverlayAlias.id.asc())
            )
        ).scalars().all()
    )

    alias_map: dict[int, list[str]] = defaultdict(list)
    for alias in aliases:
        alias_map[alias.overlay_template_id].append(str(alias.alias))
    return [(template, alias_map.get(template.id, [])) for template in templates]


async def get_overlay_template_by_text(
    db: AsyncSession,
    *,
    subject_area: str,
    topic_key: str,
    question_text: str,
) -> DiagnosisOverlayTemplate | None:
    return await db.scalar(
        select(DiagnosisOverlayTemplate)
        .where(
            DiagnosisOverlayTemplate.subject_area == subject_area,
            DiagnosisOverlayTemplate.topic_key == topic_key,
            DiagnosisOverlayTemplate.text == question_text,
        )
        .order_by(desc(DiagnosisOverlayTemplate.id))
    )


async def create_overlay_template(
    db: AsyncSession,
    *,
    template_id: str,
    subject_area: str,
    topic_key: str,
    topic_family: str,
    question_role: str,
    text: str,
    aliases: list[str],
    skills: dict[str, float],
    misconception_probes: dict[str, float],
    reference_answers: list[str],
    promotion_confidence: float,
    promotion_mode: str,
    active: bool,
    source_question_batch_id: int | None,
    source_question_index: int | None,
    source_question_text: str | None,
) -> DiagnosisOverlayTemplate:
    existing = await get_overlay_template_by_text(
        db,
        subject_area=subject_area,
        topic_key=topic_key,
        question_text=text,
    )
    if existing is not None:
        if active and not existing.active:
            existing.active = True
            existing.promotion_mode = promotion_mode
            existing.promotion_confidence = promotion_confidence
        await db.flush()
        return existing

    template = DiagnosisOverlayTemplate(
        template_id=template_id,
        subject_area=subject_area,
        topic_key=topic_key,
        topic_family=topic_family,
        question_role=question_role,
        text=text,
        skills=dict(skills),
        misconception_probes=dict(misconception_probes),
        reference_answers=list(reference_answers),
        promotion_confidence=promotion_confidence,
        promotion_mode=promotion_mode,
        active=active,
        source_question_batch_id=source_question_batch_id,
        source_question_index=source_question_index,
        source_question_text=source_question_text,
    )
    db.add(template)
    await db.flush()

    for alias_text in dict.fromkeys([text, *aliases]):
        if not alias_text:
            continue
        db.add(
            DiagnosisOverlayAlias(
                overlay_template_id=template.id,
                alias=alias_text,
            )
        )
    await db.flush()
    return template


async def upsert_canonicalization_audit(
    db: AsyncSession,
    *,
    question_batch_id: int,
    question_index: int,
    question_text: str,
    matched_template_id: str | None,
    match_source: str | None,
    similarity_score: float | None,
    inferred_question_role: str | None,
    inferred_skills: dict[str, float] | None,
    inferred_misconception_probes: dict[str, float] | None,
    promotion_decision: str,
    promotion_confidence: float | None,
    overlay_template_id: int | None,
    status: str = "completed",
) -> DiagnosisCanonicalizationAudit:
    audit = await db.scalar(
        select(DiagnosisCanonicalizationAudit).where(
            DiagnosisCanonicalizationAudit.question_batch_id == question_batch_id,
            DiagnosisCanonicalizationAudit.question_index == question_index,
        )
    )
    if audit is None:
        audit = DiagnosisCanonicalizationAudit(
            question_batch_id=question_batch_id,
            question_index=question_index,
            question_text=question_text,
        )
        db.add(audit)

    audit.question_text = question_text
    audit.matched_template_id = matched_template_id
    audit.match_source = match_source
    audit.similarity_score = similarity_score
    audit.inferred_question_role = inferred_question_role
    audit.inferred_skills = dict(inferred_skills or {})
    audit.inferred_misconception_probes = dict(inferred_misconception_probes or {})
    audit.promotion_decision = promotion_decision
    audit.promotion_confidence = promotion_confidence
    audit.overlay_template_id = overlay_template_id
    audit.status = status
    await db.flush()
    return audit


async def get_canonicalization_audits(db: AsyncSession, question_batch_id: int) -> list[DiagnosisCanonicalizationAudit]:
    return list(
        (
            await db.execute(
                select(DiagnosisCanonicalizationAudit)
                .where(DiagnosisCanonicalizationAudit.question_batch_id == question_batch_id)
                .order_by(DiagnosisCanonicalizationAudit.question_index.asc())
            )
        ).scalars().all()
    )


async def persist_diagnosis_submission(
    db: AsyncSession,
    *,
    session_id: str,
    question_batch_id: int | None,
    topic: str,
    subject_area: str,
    questions: list[str],
    answers: list[str],
    response_times_sec: list[float] | None,
    canonical_question_ids: list[str | None],
    confidence_self_report: str | None,
    live_result: DiagnosisResult,
    live_model_source: str,
    shadow_model_source: str | None,
    shadow_model_confidence: float | None,
    shadow_result: dict | None,
    shadow_status: str,
) -> DiagnosisRun:
    run = DiagnosisRun(
        session_id=session_id,
        question_batch_id=question_batch_id,
        topic=topic,
        subject_area=subject_area,
        canonical_question_ids=list(canonical_question_ids),
        confidence_self_report=confidence_self_report,
        live_model_source=live_model_source,
        live_model_confidence=live_result.diagnostic_confidence,
        live_result=live_result.model_dump(mode="json"),
        shadow_model_source=shadow_model_source,
        shadow_model_confidence=shadow_model_confidence,
        shadow_result=shadow_result,
        shadow_status=shadow_status,
        materialization_status="pending",
    )
    db.add(run)
    await db.flush()

    times = response_times_sec or []
    for index, question in enumerate(questions):
        db.add(
            DiagnosticResponse(
                session_id=session_id,
                diagnosis_run_id=run.id,
                question_index=index,
                canonical_question_id=canonical_question_ids[index] if index < len(canonical_question_ids) else None,
                question=question,
                answer=answers[index] if index < len(answers) else "",
                response_time_sec=times[index] if index < len(times) else None,
            )
        )

    session_row = await db.scalar(select(SessionTable).where(SessionTable.id == session_id))
    if session_row is not None:
        session_row.subject_area = subject_area
        session_row.learner_level = live_result.learner_level.value
        session_row.missing_prerequisites = list(live_result.missing_prerequisites)
        session_row.misconception_labels = list(live_result.misconception_labels)
        session_row.teaching_strategy = live_result.recommended_teaching_strategy.value
        session_row.phase = "planning"

    return run


async def get_diagnosis_run(db: AsyncSession, diagnosis_run_id: int | None) -> DiagnosisRun | None:
    if diagnosis_run_id is None:
        return None
    return await db.scalar(select(DiagnosisRun).where(DiagnosisRun.id == diagnosis_run_id))


async def get_diagnostic_responses_for_run(db: AsyncSession, diagnosis_run_id: int) -> list[DiagnosticResponse]:
    return list(
        (
            await db.execute(
                select(DiagnosticResponse)
                .where(DiagnosticResponse.diagnosis_run_id == diagnosis_run_id)
                .order_by(DiagnosticResponse.question_index.asc())
            )
        ).scalars().all()
    )


async def save_materialized_record(
    db: AsyncSession,
    *,
    diagnosis_run_id: int,
    question_batch_id: int | None,
    session_id: str,
    subject_area: str,
    topic: str,
    canonical_question_ids: list[str | None],
    canonical_sources: list[str | None],
    canonical_confidences: list[float | None],
    unresolved_question_indices: list[int],
    payload: dict,
) -> DiagnosisMaterializedRecord:
    record = await db.scalar(
        select(DiagnosisMaterializedRecord).where(DiagnosisMaterializedRecord.diagnosis_run_id == diagnosis_run_id)
    )
    if record is None:
        record = DiagnosisMaterializedRecord(
            diagnosis_run_id=diagnosis_run_id,
            question_batch_id=question_batch_id,
            session_id=session_id,
            subject_area=subject_area,
            topic=topic,
            payload={},
        )
        db.add(record)

    record.question_batch_id = question_batch_id
    record.session_id = session_id
    record.subject_area = subject_area
    record.topic = topic
    record.canonical_question_ids = list(canonical_question_ids)
    record.canonical_sources = list(canonical_sources)
    record.canonical_confidences = list(canonical_confidences)
    record.unresolved_question_indices = list(unresolved_question_indices)
    record.payload = dict(payload)
    await db.flush()

    run = await get_diagnosis_run(db, diagnosis_run_id)
    if run is not None:
        run.canonical_question_ids = list(canonical_question_ids)
        run.materialization_status = "completed"
    return record


async def mark_diagnosis_run_materialization_status(
    db: AsyncSession,
    diagnosis_run_id: int,
    status: str,
) -> None:
    run = await get_diagnosis_run(db, diagnosis_run_id)
    if run is not None:
        run.materialization_status = status
        await db.flush()


async def export_diagnosis_dataset_rows(
    db: AsyncSession,
    *,
    subject_area: str | None = None,
) -> list[dict]:
    query = select(DiagnosisRun).order_by(DiagnosisRun.created_at.asc())
    if subject_area:
        query = query.where(DiagnosisRun.subject_area == subject_area)

    runs = list((await db.execute(query)).scalars().all())
    if not runs:
        return []

    run_ids = [run.id for run in runs]
    materialized_records = list(
        (
            await db.execute(
                select(DiagnosisMaterializedRecord)
                .where(DiagnosisMaterializedRecord.diagnosis_run_id.in_(run_ids))
            )
        ).scalars().all()
    )
    materialized_map = {record.diagnosis_run_id: record for record in materialized_records}

    responses = list(
        (
            await db.execute(
                select(DiagnosticResponse)
                .where(DiagnosticResponse.diagnosis_run_id.in_(run_ids))
                .order_by(DiagnosticResponse.diagnosis_run_id.asc(), DiagnosticResponse.question_index.asc())
            )
        ).scalars().all()
    )

    grouped: dict[int, list[DiagnosticResponse]] = defaultdict(list)
    for response in responses:
        if response.diagnosis_run_id is not None:
            grouped[response.diagnosis_run_id].append(response)

    exported: list[dict] = []
    for run in runs:
        materialized = materialized_map.get(run.id)
        if materialized is not None and materialized.payload:
            exported.append(dict(materialized.payload))
            continue

        run_responses = grouped.get(run.id, [])
        live_result = dict(run.live_result or {})
        exported.append(
            {
                "session_id": run.session_id,
                "subject_area": run.subject_area,
                "topic": run.topic,
                "canonical_question_ids": list(run.canonical_question_ids or []),
                "questions": [response.question or "" for response in run_responses],
                "answers": [response.answer or "" for response in run_responses],
                "response_times_sec": [response.response_time_sec for response in run_responses],
                "confidence_self_report": run.confidence_self_report,
                "labels": {
                    "learner_level": live_result.get("learner_level"),
                    "missing_prerequisites": list(live_result.get("missing_prerequisites") or []),
                    "misconception_labels": list(live_result.get("misconception_labels") or []),
                    "recommended_teaching_strategy": live_result.get("recommended_teaching_strategy"),
                },
                "live_model_source": run.live_model_source,
                "shadow_model_source": run.shadow_model_source,
                "shadow_status": run.shadow_status,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        )

    return exported


async def get_background_job_by_dedupe_key(db: AsyncSession, dedupe_key: str) -> DiagnosisBackgroundJob | None:
    return await db.scalar(
        select(DiagnosisBackgroundJob).where(DiagnosisBackgroundJob.dedupe_key == dedupe_key)
    )


async def get_background_job(db: AsyncSession, job_id: int | None) -> DiagnosisBackgroundJob | None:
    if job_id is None:
        return None
    return await db.scalar(
        select(DiagnosisBackgroundJob).where(DiagnosisBackgroundJob.id == job_id)
    )


async def create_background_job(
    db: AsyncSession,
    *,
    job_type: str,
    dedupe_key: str,
    session_id: str | None,
    question_batch_id: int | None,
    diagnosis_run_id: int | None,
    payload: dict,
    max_attempts: int,
) -> DiagnosisBackgroundJob:
    job = DiagnosisBackgroundJob(
        job_type=job_type,
        dedupe_key=dedupe_key,
        session_id=session_id,
        question_batch_id=question_batch_id,
        diagnosis_run_id=diagnosis_run_id,
        payload=dict(payload),
        max_attempts=max_attempts,
        status="queued",
    )
    db.add(job)
    await db.flush()
    return job


async def list_recoverable_background_jobs(db: AsyncSession) -> list[DiagnosisBackgroundJob]:
    return list(
        (
            await db.execute(
                select(DiagnosisBackgroundJob).where(
                    DiagnosisBackgroundJob.status.in_(["queued", "running"])
                )
            )
        ).scalars().all()
    )
