"""0001_initial — create all 7 tables

Revision ID: 0001
Revises: None
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "done", "failed", name="job_status"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by", sa.Enum("manual", "reeval", name="eval_trigger"), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("test_case_id", sa.String(64), nullable=False),
        sa.Column("category", sa.Enum("baseline", "ambiguous", "adversarial", name="eval_category"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("agent_prompts", postgresql.JSONB(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_runs_run_group_id", "eval_runs", ["run_group_id"])

    op.create_table(
        "agent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.Enum("agent_start", "token", "tool_call", "tool_result", "budget_update", "agent_done", "policy_violation", "graph_edge", name="agent_event_type"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("policy_violation", sa.Boolean(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_events_job_id", "agent_events", ["job_id"])

    op.create_table(
        "tool_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("retry_number", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_call_logs_job_id", "tool_call_logs", ["job_id"])

    op.create_table(
        "prompt_rewrites",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("old_prompt", sa.Text(), nullable=False),
        sa.Column("new_prompt", sa.Text(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", name="rewrite_status"), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(256), nullable=True),
        sa.Column("performance_delta", postgresql.JSONB(), nullable=True),
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("rewrite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.Enum("approved", "rejected", name="approval_decision"), nullable=False),
        sa.Column("decided_by", sa.String(256), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["rewrite_id"], ["prompt_rewrites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_rewrite_id", "approvals", ["rewrite_id"])

    op.create_table(
        "eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_cases_eval_run_id", "eval_cases", ["eval_run_id"])


def downgrade() -> None:
    op.drop_table("eval_cases")
    op.drop_table("approvals")
    op.drop_table("prompt_rewrites")
    op.drop_table("tool_call_logs")
    op.drop_table("agent_events")
    op.drop_table("eval_runs")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS approval_decision")
    op.execute("DROP TYPE IF EXISTS rewrite_status")
    op.execute("DROP TYPE IF EXISTS eval_category")
    op.execute("DROP TYPE IF EXISTS eval_trigger")
    op.execute("DROP TYPE IF EXISTS agent_event_type")
    op.execute("DROP TYPE IF EXISTS job_status")

