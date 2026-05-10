import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.responses import ErrorResponse, TraceResponse
from db.queries import get_job, get_agent_events, get_tool_call_logs

router = APIRouter(tags=["Trace"])


@router.get("/trace/{job_id}")
async def get_trace(job_id: str, db: AsyncSession = Depends(get_db)):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_JOB_ID",
                message=f"'{job_id}' is not a valid UUID.",
                job_id=job_id,
            ).model_dump(),
        )

    job = await get_job(db, job_uuid)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="JOB_NOT_FOUND",
                message=f"No job found with ID {job_id}.",
                job_id=job_id,
            ).model_dump(),
        )

    agent_events_raw = await get_agent_events(db, job_uuid)
    tool_logs = await get_tool_call_logs(db, job_id=job_uuid)

    agent_events = [
        {
            "id": str(e.id),
            "agent_id": e.agent_id,
            "event_type": e.event_type,
            "input_hash": e.input_hash,
            "output_hash": e.output_hash,
            "latency_ms": e.latency_ms,
            "token_count": e.token_count,
            "payload": e.payload or {},
            "policy_violation": e.policy_violation,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in agent_events_raw
    ]

    graph_edges = [
        {
            "from_node": entry.get("from", entry.get("agent", "")),
            "to_node": entry.get("to", entry.get("next", "")),
            "reasoning": entry.get("reasoning", entry.get("reason", "")),
            "timestamp": entry.get("timestamp", ""),
        }
        for e in agent_events_raw
        if e.event_type == "graph_edge" and e.payload
        for entry in ([e.payload] if isinstance(e.payload, dict) else [])
        if "next" in entry or "to" in entry
    ]

    tool_calls = [
        {
            "tool_name": t.tool_name,
            "agent_id": t.agent_id,
            "input": t.input or {},
            "output": t.output,
            "latency_ms": t.latency_ms,
            "accepted": t.accepted,
            "retry_number": t.retry_number,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        }
        for t in tool_logs
    ]

    return TraceResponse(
        job_id=job_id,
        status=job.status,
        query=job.query,
        final_answer=job.final_answer,
        agent_events=agent_events,
        tool_calls=tool_calls,
        graph_edges=graph_edges,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )

