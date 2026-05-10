import hashlib
import json
import uuid
from datetime import datetime, UTC
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AgentEvent, Approval, EvalCase, EvalRun, Job, PromptRewrite, ToolCallLog


def sha256_hex(data: dict | str) -> str:
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    raw = json.dumps(data, sort_keys=True, default=json_serial) if not isinstance(data, str) else data
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_job(session: AsyncSession, job_id: uuid.UUID, query: str) -> Job:
    from sqlalchemy import text
    result = await session.execute(
        text("INSERT INTO jobs (id, query, status) VALUES (:id, :query, 'pending'::job_status) RETURNING created_at"),
        {"id": job_id, "query": query}
    )
    row = result.fetchone()
    await session.commit()
    job = Job(id=job_id, query=query, status="pending")
    if row:
        job.created_at = row[0]
    return job


async def update_job_status(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    final_answer: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    from sqlalchemy import text
    completed_val = completed_at or datetime.now(UTC)
    if status in ("done", "failed"):
        sql = f"UPDATE jobs SET status = '{status}'::job_status, completed_at = :completed_at, final_answer = COALESCE(:final_answer, final_answer) WHERE id = :job_id"
        await session.execute(text(sql), {"completed_at": completed_val, "final_answer": final_answer, "job_id": job_id})
    else:
        sql = f"UPDATE jobs SET status = '{status}'::job_status, final_answer = COALESCE(:final_answer, final_answer) WHERE id = :job_id"
        await session.execute(text(sql), {"final_answer": final_answer, "job_id": job_id})
    await session.commit()


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def get_all_jobs(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[Job]:
    result = await session.execute(
        select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


async def write_agent_event(
    session: AsyncSession,
    job_id: uuid.UUID,
    agent_id: str,
    event_type: str,
    input_hash: str,
    output_hash: str | None = None,
    latency_ms: float = 0.0,
    token_count: int = 0,
    payload: dict | None = None,
    policy_violation: bool = False,
) -> AgentEvent:
    event = AgentEvent(
        job_id=job_id,
        agent_id=agent_id,
        event_type=event_type,
        input_hash=input_hash,
        output_hash=output_hash,
        latency_ms=latency_ms,
        token_count=token_count,
        payload=payload or {},
        policy_violation=policy_violation,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_agent_events(
    session: AsyncSession,
    job_id: uuid.UUID,
    agent_id: str | None = None,
    event_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[AgentEvent]:
    conditions = [AgentEvent.job_id == job_id]
    if agent_id:
        conditions.append(AgentEvent.agent_id == agent_id)
    if event_type:
        conditions.append(AgentEvent.event_type == event_type)
    result = await session.execute(
        select(AgentEvent)
        .where(*conditions)
        .order_by(AgentEvent.timestamp.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def write_tool_call_log(
    session: AsyncSession,
    job_id: uuid.UUID,
    agent_id: str,
    tool_name: str,
    input: dict,
    output: dict | None,
    latency_ms: float,
    accepted: bool | None,
    retry_number: int = 0,
) -> ToolCallLog:
    log = ToolCallLog(
        job_id=job_id,
        agent_id=agent_id,
        tool_name=tool_name,
        input=input,
        output=output,
        latency_ms=latency_ms,
        accepted=accepted,
        retry_number=retry_number,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_tool_call_logs(
    session: AsyncSession,
    job_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[ToolCallLog]:
    conditions = []
    if job_id:
        conditions.append(ToolCallLog.job_id == job_id)
    if tool_name:
        conditions.append(ToolCallLog.tool_name == tool_name)
    result = await session.execute(
        select(ToolCallLog)
        .where(*conditions)
        .order_by(ToolCallLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def save_eval_run(session: AsyncSession, run: EvalRun) -> EvalRun:
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def save_eval_cases(session: AsyncSession, cases: list[EvalCase]) -> list[EvalCase]:
    session.add_all(cases)
    await session.commit()
    for c in cases:
        await session.refresh(c)
    return cases


async def get_eval_run(session: AsyncSession, run_id: uuid.UUID) -> EvalRun | None:
    result = await session.execute(select(EvalRun).where(EvalRun.id == run_id))
    return result.scalar_one_or_none()


async def get_latest_eval_runs(session: AsyncSession) -> list[EvalRun]:
    subquery = (
        select(EvalRun.run_group_id)
        .order_by(EvalRun.timestamp.desc())
        .limit(1)
        .scalar_subquery()
    )
    result = await session.execute(
        select(EvalRun).where(EvalRun.run_group_id == subquery)
    )
    return list(result.scalars().all())


async def get_eval_cases(session: AsyncSession, eval_run_id: uuid.UUID) -> list[EvalCase]:
    result = await session.execute(
        select(EvalCase).where(EvalCase.eval_run_id == eval_run_id)
    )
    return list(result.scalars().all())


async def save_prompt_rewrite(session: AsyncSession, rewrite: PromptRewrite) -> PromptRewrite:
    session.add(rewrite)
    await session.commit()
    await session.refresh(rewrite)
    return rewrite


async def get_rewrite_by_id(session: AsyncSession, rewrite_id: uuid.UUID) -> PromptRewrite | None:
    result = await session.execute(
        select(PromptRewrite).where(PromptRewrite.id == rewrite_id)
    )
    return result.scalar_one_or_none()


async def get_latest_approved_prompt(session: AsyncSession, agent_id: str) -> PromptRewrite | None:
    result = await session.execute(
        select(PromptRewrite)
        .where(PromptRewrite.agent_id == agent_id, PromptRewrite.status == "approved")
        .order_by(PromptRewrite.decided_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_pending_rewrites(session: AsyncSession) -> list[PromptRewrite]:
    from sqlalchemy import text
    result = await session.execute(
        text("SELECT * FROM prompt_rewrites WHERE status = 'pending' ORDER BY proposed_at")
    )
    return [PromptRewrite(**dict(row._mapping)) for row in result.fetchall()]


async def approve_rewrite(
    session: AsyncSession,
    rewrite_id: uuid.UUID,
    decided_by: str,
) -> PromptRewrite | None:
    rewrite = await get_rewrite_by_id(session, rewrite_id)
    if not rewrite:
        return None
    rewrite.status = "approved"
    rewrite.decided_at = datetime.now(UTC)
    rewrite.decided_by = decided_by
    approval = Approval(rewrite_id=rewrite_id, decision="approved", decided_by=decided_by)
    session.add(approval)
    await session.commit()
    await session.refresh(rewrite)
    return rewrite


async def reject_rewrite(
    session: AsyncSession,
    rewrite_id: uuid.UUID,
    decided_by: str,
) -> PromptRewrite | None:
    rewrite = await get_rewrite_by_id(session, rewrite_id)
    if not rewrite:
        return None
    rewrite.status = "rejected"
    rewrite.decided_at = datetime.now(UTC)
    rewrite.decided_by = decided_by
    approval = Approval(rewrite_id=rewrite_id, decision="rejected", decided_by=decided_by)
    session.add(approval)
    await session.commit()
    await session.refresh(rewrite)
    return rewrite