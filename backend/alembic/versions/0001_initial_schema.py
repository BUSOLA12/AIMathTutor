"""Initial schema — sessions, diagnostic_responses, lesson_events, evaluation_results

Revision ID: 0001
Revises: —
Create Date: 2026-03-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── sessions ──────────────────────────────────────────────────────────────
    # Core record for a tutoring session. Created on POST /api/session/create.
    # live phase tracking lives in Redis; this is the durable audit copy.
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("subject_area", sa.String(), nullable=True),
        sa.Column("learner_level", sa.String(), nullable=True),
        sa.Column("missing_prerequisites", sa.JSON(), nullable=True),
        sa.Column("misconception_labels", sa.JSON(), nullable=True),
        sa.Column("teaching_strategy", sa.String(), nullable=True),
        sa.Column("phase", sa.String(), nullable=True, server_default="input"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index for time-based analytics queries
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])

    # ── diagnostic_responses ──────────────────────────────────────────────────
    # Each row = one question + student answer pair from the diagnosis step.
    # Stored here for future ML training data collection.
    op.create_table(
        "diagnostic_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("response_time_sec", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnostic_responses_session_id",
        "diagnostic_responses",
        ["session_id"],
    )

    # ── lesson_events ─────────────────────────────────────────────────────────
    # Append-only log of tutoring events:
    #   event_type = "section_delivered" | "interruption" | "checkpoint"
    # content stores the full LLM output + board events as JSON.
    op.create_table(
        "lesson_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lesson_events_session_id",
        "lesson_events",
        ["session_id"],
    )

    # ── evaluation_results ────────────────────────────────────────────────────
    # Stores the scored post-lesson evaluation for each session.
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("understanding_summary", sa.JSON(), nullable=True),
        sa.Column("remaining_gaps", sa.JSON(), nullable=True),
        sa.Column("recommended_next_step", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_session_id",
        "evaluation_results",
        ["session_id"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order (children before parent)
    op.drop_index("ix_evaluation_results_session_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")

    op.drop_index("ix_lesson_events_session_id", table_name="lesson_events")
    op.drop_table("lesson_events")

    op.drop_index("ix_diagnostic_responses_session_id", table_name="diagnostic_responses")
    op.drop_table("diagnostic_responses")

    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_table("sessions")
