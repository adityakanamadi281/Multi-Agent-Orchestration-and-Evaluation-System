"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        'jobs',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='job_status', create_type=False), nullable=False, server_default='queued'),
        sa.Column('final_answer', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'agent_events',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id'), nullable=False, index=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('output_hash', sa.String(64), nullable=True),
        sa.Column('latency_ms', sa.Float(), server_default=sa.text('0')),
        sa.Column('token_count', sa.Integer(), server_default=sa.text('0')),
        sa.Column('payload', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('policy_violation', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'tool_call_logs',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id'), nullable=False, index=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('tool_name', sa.String(50), nullable=False),
        sa.Column('input', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('output', JSONB(), nullable=True),
        sa.Column('latency_ms', sa.Float(), server_default=sa.text('0')),
        sa.Column('accepted', sa.Boolean(), nullable=True),
        sa.Column('retry_number', sa.Integer(), server_default=sa.text('0')),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'eval_runs',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('run_group_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('prompt_snapshot', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('total_cases', sa.Integer(), server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'eval_cases',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('eval_run_id', UUID(as_uuid=True), sa.ForeignKey('eval_runs.id'), nullable=False, index=True),
        sa.Column('test_case_id', sa.String(10), nullable=False),
        sa.Column('category', sa.Enum('baseline', 'ambiguous', 'adversarial', name='eval_category', create_type=False), nullable=False),
        sa.Column('scores', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('tool_call_log', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('agent_outputs', JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'prompt_rewrites',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('dimension', sa.String(50), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False),
        sa.Column('proposed_prompt', sa.Text(), nullable=False),
        sa.Column('diff_hunks', JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='rewrite_status', create_type=False), server_default='pending'),
        sa.Column('score_before', sa.Float(), nullable=True),
        sa.Column('score_after', sa.Float(), nullable=True),
        sa.Column('proposed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'approvals',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('rewrite_id', UUID(as_uuid=True), sa.ForeignKey('prompt_rewrites.id'), nullable=False, index=True),
        sa.Column('decision', sa.Enum('approved', 'rejected', name='approval_decision', create_type=False), nullable=False),
        sa.Column('decided_by', sa.String(100), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('approvals')
    op.drop_table('prompt_rewrites')
    op.drop_table('eval_cases')
    op.drop_table('eval_runs')
    op.drop_table('tool_call_logs')
    op.drop_table('agent_events')
    op.drop_table('jobs')
    op.execute('DROP TYPE IF EXISTS job_status')
    op.execute('DROP TYPE IF EXISTS eval_category')
    op.execute('DROP TYPE IF EXISTS rewrite_status')
    op.execute('DROP TYPE IF EXISTS approval_decision')