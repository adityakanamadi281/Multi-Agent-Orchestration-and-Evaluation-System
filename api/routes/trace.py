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
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_JOB_ID",
                message="Not a valid UUID.",
                job_id=None,
            ).model_dump(),
        )

    job = await get_job(db, uid)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="TRACE_NOT_FOUND",
                message="No job with that ID.",
                job_id=job_id,
            ).model_dump(),
        )

    events = await get_agent_events(db, uid)
    tool_calls = await get_tool_call_logs(db, uid)
    graph_edges = [
        {
            "from_node": e.payload.get("from_node", ""),
            "to_node": e.payload.get("to_node", ""),
            "reasoning": e.payload.get("reasoning", ""),
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
        if e.event_type == "graph_edge"
    ]

    return TraceResponse(
        job_id=str(job.id),
        status=job.status,
        query=job.query,
        final_answer=job.final_answer,
        agent_events=[
            {
                "id": str(e.id),
                "agent_id": e.agent_id,
                "event_type": e.event_type,
                "latency_ms": e.latency_ms,
                "token_count": e.token_count,
                "payload": e.payload or {},
                "policy_violation": e.policy_violation,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in events
        ],
        tool_calls=[
            {
                "tool_name": t.tool_name,
                "agent_id": t.agent_id,
                "input": t.input or {},
                "output": t.output or {},
                "latency_ms": t.latency_ms,
                "accepted": t.accepted,
                "retry_number": t.retry_number,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            }
            for t in tool_calls
        ],
        graph_edges=graph_edges,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )
