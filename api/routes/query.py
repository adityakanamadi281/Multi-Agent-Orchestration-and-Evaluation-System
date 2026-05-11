import json
import uuid
import asyncio
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_db
from api.schemas.responses import ErrorResponse, QueryQueued, QueryRequest
from db.queries import create_job

router = APIRouter(tags=["Query"])


@router.post("/query")
async def submit_query(request: QueryRequest, db: AsyncSession = Depends(get_db)):
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="QUERY_EMPTY",
                message="The query field must not be blank.",
                job_id=None,
            ).model_dump(),
        )

    job_id = uuid.uuid4()
    await create_job(db, job_id, request.query)

    from arq import create_pool
    from arq.connections import RedisSettings
    from core.config import settings
    import redis.asyncio as aioredis

    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        await arq_pool.enqueue_job("process_query_job", str(job_id), request.query)
    except Exception:
        await arq_pool.close()
        raise

    if not request.stream:
        await arq_pool.close()
        return QueryQueued(job_id=str(job_id), status="pending")

    await arq_pool.close()
    r = aioredis.from_url(settings.REDIS_URL)

    async def event_generator():
        pubsub = r.pubsub()
        channel = f"job:{job_id}"
        await pubsub.subscribe(channel)

        yield (
            "data: "
            + json.dumps({
                "job_id": str(job_id),
                "agent_id": "system",
                "event_type": "job_queued",
                "data": {"query": request.query},
                "timestamp": datetime.now(UTC).isoformat(),
            })
            + "\n\n"
        )

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                raw = message["data"]
                if isinstance(raw, bytes):
                    raw = raw.decode()
                yield f"data: {raw}\n\n"
                try:
                    parsed = json.loads(raw)
                    if parsed.get("event_type") in ("job_done", "job_failed"):
                        break
                except Exception:
                    pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
