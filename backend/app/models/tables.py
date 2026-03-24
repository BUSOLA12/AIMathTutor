from sqlalchemy import Boolean, Column, String, Float, Integer, JSON, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    topic = Column(String, nullable=False)
    target_type = Column(String)
    subject_area = Column(String)
    learner_level = Column(String)
    missing_prerequisites = Column(JSON, default=list)
    misconception_labels = Column(JSON, default=list)
    teaching_strategy = Column(String)
    phase = Column(String, default="input")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DiagnosticResponse(Base):
    __tablename__ = "diagnostic_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    diagnosis_run_id = Column(Integer, ForeignKey("diagnosis_runs.id"), nullable=True)
    question_index = Column(Integer, nullable=True)
    canonical_question_id = Column(String, nullable=True)
    question = Column(Text)
    answer = Column(Text)
    response_time_sec = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DiagnosisRun(Base):
    __tablename__ = "diagnosis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    question_batch_id = Column(Integer, ForeignKey("diagnosis_question_batches.id"), nullable=True)
    topic = Column(String, nullable=False)
    subject_area = Column(String, nullable=False)
    canonical_question_ids = Column(JSON, default=list)
    confidence_self_report = Column(String, nullable=True)
    live_model_source = Column(String, nullable=False)
    live_model_confidence = Column(Float, nullable=True)
    live_result = Column(JSON, nullable=False)
    shadow_model_source = Column(String, nullable=True)
    shadow_model_confidence = Column(Float, nullable=True)
    shadow_result = Column(JSON, nullable=True)
    shadow_status = Column(String, nullable=True)
    materialization_status = Column(String, nullable=True, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DiagnosisQuestionBatch(Base):
    __tablename__ = "diagnosis_question_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    topic = Column(String, nullable=False)
    topic_key = Column(String, nullable=False)
    subject_area = Column(String, nullable=False)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False, default="issued")
    questions = Column(JSON, default=list)
    question_count = Column(Integer, nullable=False, default=0)
    canonicalization_status = Column(String, nullable=False, default="pending")
    canonical_question_ids = Column(JSON, default=list)
    canonical_sources = Column(JSON, default=list)
    canonical_scores = Column(JSON, default=list)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True), nullable=True)


class DiagnosisBackgroundJob(Base):
    __tablename__ = "diagnosis_background_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    dedupe_key = Column(String, nullable=False)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    question_batch_id = Column(Integer, ForeignKey("diagnosis_question_batches.id"), nullable=True)
    diagnosis_run_id = Column(Integer, ForeignKey("diagnosis_runs.id"), nullable=True)
    payload = Column(JSON, default=dict)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    last_error = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class DiagnosisOverlayTemplate(Base):
    __tablename__ = "diagnosis_overlay_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String, nullable=False)
    subject_area = Column(String, nullable=False)
    topic_key = Column(String, nullable=False)
    topic_family = Column(String, nullable=False)
    question_role = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    skills = Column(JSON, default=dict)
    misconception_probes = Column(JSON, default=dict)
    reference_answers = Column(JSON, default=list)
    promotion_confidence = Column(Float, nullable=True)
    promotion_mode = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    source_question_batch_id = Column(Integer, ForeignKey("diagnosis_question_batches.id"), nullable=True)
    source_question_index = Column(Integer, nullable=True)
    source_question_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DiagnosisOverlayAlias(Base):
    __tablename__ = "diagnosis_overlay_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    overlay_template_id = Column(Integer, ForeignKey("diagnosis_overlay_templates.id"), nullable=False)
    alias = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DiagnosisCanonicalizationAudit(Base):
    __tablename__ = "diagnosis_canonicalization_audits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_batch_id = Column(Integer, ForeignKey("diagnosis_question_batches.id"), nullable=False)
    question_index = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    matched_template_id = Column(String, nullable=True)
    match_source = Column(String, nullable=True)
    similarity_score = Column(Float, nullable=True)
    inferred_question_role = Column(String, nullable=True)
    inferred_skills = Column(JSON, default=dict)
    inferred_misconception_probes = Column(JSON, default=dict)
    promotion_decision = Column(String, nullable=False)
    promotion_confidence = Column(Float, nullable=True)
    overlay_template_id = Column(Integer, ForeignKey("diagnosis_overlay_templates.id"), nullable=True)
    status = Column(String, nullable=False, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DiagnosisMaterializedRecord(Base):
    __tablename__ = "diagnosis_materialized_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    diagnosis_run_id = Column(Integer, ForeignKey("diagnosis_runs.id"), nullable=False)
    question_batch_id = Column(Integer, ForeignKey("diagnosis_question_batches.id"), nullable=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    subject_area = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    canonical_question_ids = Column(JSON, default=list)
    canonical_sources = Column(JSON, default=list)
    canonical_confidences = Column(JSON, default=list)
    unresolved_question_indices = Column(JSON, default=list)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class LessonEvent(Base):
    __tablename__ = "lesson_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    event_type = Column(String)   # "section_delivered" | "interruption" | "checkpoint"
    content = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    understanding_summary = Column(JSON)
    remaining_gaps = Column(JSON, default=list)
    recommended_next_step = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
