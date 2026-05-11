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

    # Create Enum types
    op.execute("CREATE TYPE job_status AS ENUM ('pending', 'running', 'done', 'failed')")
    op.execute("CREATE TYPE agent_event_type AS ENUM ('agent_start', 'token', 'tool_call', 'tool_result', 'budget_update', 'agent_done', 'policy_violation', 'graph_edge')")
    op.execute("CREATE TYPE eval_trigger AS ENUM ('manual', 'reeval')")
    op.execute("CREATE TYPE eval_category AS ENUM ('baseline', 'ambiguous', 'adversarial')")
    op.execute("CREATE TYPE rewrite_status AS ENUM ('pending', 'approved', 'rejected')")
    op.execute("CREATE TYPE approval_decision AS ENUM ('approved', 'rejected')")

    op.create_table(
        'jobs',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'done', 'failed', name='job_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('final_answer', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'agent_events',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id'), nullable=False, index=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('event_type', sa.Enum('agent_start', 'token', 'tool_call', 'tool_result', 'budget_update', 'agent_done', 'policy_violation', 'graph_edge', name='agent_event_type', create_type=False), nullable=False),
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
        sa.Column('triggered_by', sa.Enum('manual', 'reeval', name='eval_trigger', create_type=False), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('test_case_id', sa.String(50), nullable=True),
        sa.Column('category', sa.Enum('baseline', 'ambiguous', 'adversarial', name='eval_category', create_type=False), nullable=True),
        sa.Column('query', sa.Text(), nullable=True),
        sa.Column('final_answer', sa.Text(), nullable=True),
        sa.Column('scores', JSONB(), nullable=True),
        sa.Column('agent_prompts', JSONB(), nullable=True),
        sa.Column('tool_calls', JSONB(), nullable=True),
        sa.Column('job_id', UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        'eval_cases',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('eval_run_id', UUID(as_uuid=True), sa.ForeignKey('eval_runs.id'), nullable=False, index=True),
        sa.Column('dimension', sa.String(50), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('justification', sa.Text(), nullable=True),
    )

    op.create_table(
        'prompt_rewrites',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('dimension', sa.String(50), nullable=False),
        sa.Column('old_prompt', sa.Text(), nullable=True),
        sa.Column('new_prompt', sa.Text(), nullable=True),
        sa.Column('diff', sa.Text(), nullable=True),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='rewrite_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by', sa.String(100), nullable=True),
        sa.Column('performance_delta', JSONB(), nullable=True),
        sa.Column('eval_run_id', UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        'approvals',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('rewrite_id', UUID(as_uuid=True), sa.ForeignKey('prompt_rewrites.id'), nullable=False, index=True),
        sa.Column('decision', sa.Enum('approved', 'rejected', name='approval_decision', create_type=False), nullable=False),
        sa.Column('decided_by', sa.String(100), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('notes', sa.Text(), nullable=True),
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
    op.execute('DROP TYPE IF EXISTS agent_event_type')
    op.execute('DROP TYPE IF EXISTS eval_trigger')
    op.execute('DROP TYPE IF EXISTS eval_category')
    op.execute('DROP TYPE IF EXISTS rewrite_status')
    op.execute('DROP TYPE IF EXISTS approval_decision')