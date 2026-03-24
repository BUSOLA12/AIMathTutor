"""Add diagnosis question batches, background jobs, overlay templates, and materialized records

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_question_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("topic_key", sa.String(), nullable=False),
        sa.Column("subject_area", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="issued"),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("canonicalization_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("canonical_question_ids", sa.JSON(), nullable=True),
        sa.Column("canonical_sources", sa.JSON(), nullable=True),
        sa.Column("canonical_scores", sa.JSON(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_question_batches_session_id",
        "diagnosis_question_batches",
        ["session_id"],
    )

    op.create_table(
        "diagnosis_background_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("question_batch_id", sa.Integer(), nullable=True),
        sa.Column("diagnosis_run_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_batch_id"], ["diagnosis_question_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diagnosis_run_id"], ["diagnosis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_diagnosis_background_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_diagnosis_background_jobs_status",
        "diagnosis_background_jobs",
        ["status"],
    )

    op.create_table(
        "diagnosis_overlay_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.String(), nullable=False),
        sa.Column("subject_area", sa.String(), nullable=False),
        sa.Column("topic_key", sa.String(), nullable=False),
        sa.Column("topic_family", sa.String(), nullable=False),
        sa.Column("question_role", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("misconception_probes", sa.JSON(), nullable=True),
        sa.Column("reference_answers", sa.JSON(), nullable=True),
        sa.Column("promotion_confidence", sa.Float(), nullable=True),
        sa.Column("promotion_mode", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_question_batch_id", sa.Integer(), nullable=True),
        sa.Column("source_question_index", sa.Integer(), nullable=True),
        sa.Column("source_question_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["source_question_batch_id"], ["diagnosis_question_batches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", name="uq_diagnosis_overlay_templates_template_id"),
    )
    op.create_index(
        "ix_diagnosis_overlay_templates_subject_topic",
        "diagnosis_overlay_templates",
        ["subject_area", "topic_key", "active"],
    )

    op.create_table(
        "diagnosis_overlay_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("overlay_template_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["overlay_template_id"], ["diagnosis_overlay_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("overlay_template_id", "alias", name="uq_diagnosis_overlay_aliases_template_alias"),
    )

    op.create_table(
        "diagnosis_canonicalization_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question_batch_id", sa.Integer(), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("matched_template_id", sa.String(), nullable=True),
        sa.Column("match_source", sa.String(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("inferred_question_role", sa.String(), nullable=True),
        sa.Column("inferred_skills", sa.JSON(), nullable=True),
        sa.Column("inferred_misconception_probes", sa.JSON(), nullable=True),
        sa.Column("promotion_decision", sa.String(), nullable=False),
        sa.Column("promotion_confidence", sa.Float(), nullable=True),
        sa.Column("overlay_template_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["question_batch_id"], ["diagnosis_question_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["overlay_template_id"], ["diagnosis_overlay_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_batch_id", "question_index", name="uq_diagnosis_canonicalization_audits_batch_index"),
    )

    op.create_table(
        "diagnosis_materialized_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("diagnosis_run_id", sa.Integer(), nullable=False),
        sa.Column("question_batch_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("subject_area", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("canonical_question_ids", sa.JSON(), nullable=True),
        sa.Column("canonical_sources", sa.JSON(), nullable=True),
        sa.Column("canonical_confidences", sa.JSON(), nullable=True),
        sa.Column("unresolved_question_indices", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["diagnosis_run_id"], ["diagnosis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_batch_id"], ["diagnosis_question_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnosis_run_id", name="uq_diagnosis_materialized_records_run_id"),
    )

    op.add_column(
        "diagnosis_runs",
        sa.Column("question_batch_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "diagnosis_runs",
        sa.Column("materialization_status", sa.String(), nullable=True, server_default="pending"),
    )
    op.create_foreign_key(
        "fk_diagnosis_runs_question_batch_id",
        "diagnosis_runs",
        "diagnosis_question_batches",
        ["question_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_diagnosis_runs_question_batch_id", "diagnosis_runs", type_="foreignkey")
    op.drop_column("diagnosis_runs", "materialization_status")
    op.drop_column("diagnosis_runs", "question_batch_id")

    op.drop_table("diagnosis_materialized_records")
    op.drop_table("diagnosis_canonicalization_audits")
    op.drop_table("diagnosis_overlay_aliases")
    op.drop_index("ix_diagnosis_overlay_templates_subject_topic", table_name="diagnosis_overlay_templates")
    op.drop_table("diagnosis_overlay_templates")
    op.drop_index("ix_diagnosis_background_jobs_status", table_name="diagnosis_background_jobs")
    op.drop_table("diagnosis_background_jobs")
    op.drop_index("ix_diagnosis_question_batches_session_id", table_name="diagnosis_question_batches")
    op.drop_table("diagnosis_question_batches")
