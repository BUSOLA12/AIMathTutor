"""Add diagnosis_runs and canonical question metadata

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("subject_area", sa.String(), nullable=False),
        sa.Column("canonical_question_ids", sa.JSON(), nullable=True),
        sa.Column("confidence_self_report", sa.String(), nullable=True),
        sa.Column("live_model_source", sa.String(), nullable=False),
        sa.Column("live_model_confidence", sa.Float(), nullable=True),
        sa.Column("live_result", sa.JSON(), nullable=False),
        sa.Column("shadow_model_source", sa.String(), nullable=True),
        sa.Column("shadow_model_confidence", sa.Float(), nullable=True),
        sa.Column("shadow_result", sa.JSON(), nullable=True),
        sa.Column("shadow_status", sa.String(), nullable=True),
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
        "ix_diagnosis_runs_session_id",
        "diagnosis_runs",
        ["session_id"],
    )

    op.add_column(
        "diagnostic_responses",
        sa.Column("diagnosis_run_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "diagnostic_responses",
        sa.Column("question_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "diagnostic_responses",
        sa.Column("canonical_question_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_diagnostic_responses_diagnosis_run_id",
        "diagnostic_responses",
        "diagnosis_runs",
        ["diagnosis_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_diagnostic_responses_diagnosis_run_id",
        "diagnostic_responses",
        type_="foreignkey",
    )
    op.drop_column("diagnostic_responses", "canonical_question_id")
    op.drop_column("diagnostic_responses", "question_index")
    op.drop_column("diagnostic_responses", "diagnosis_run_id")

    op.drop_index("ix_diagnosis_runs_session_id", table_name="diagnosis_runs")
    op.drop_table("diagnosis_runs")
