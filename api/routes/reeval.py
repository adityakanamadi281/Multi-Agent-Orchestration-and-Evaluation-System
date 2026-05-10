import uuid as _uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_db
from api.schemas.responses import ReevalRequest, ReevalResponse
from arq import create_pool
from arq.connections import RedisSettings
from core.config import settings

router = APIRouter(tags=["Evaluation"])


@router.post("/re-eval")
async def trigger_reeval(
    request: ReevalRequest,
    db: AsyncSession = Depends(get_db),
):
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        reeval_job_id = str(_uuid.uuid4())
        await arq_pool.enqueue_job(
            "run_targeted_reeval",
            request.test_case_ids,
            request.approved_rewrite_ids,
            _job_id=reeval_job_id,
        )
    finally:
        await arq_pool.close()

    return ReevalResponse(
        reeval_job_id=reeval_job_id,
        test_cases=len(request.test_case_ids) if request.test_case_ids else 0,
        status="queued",
    )
