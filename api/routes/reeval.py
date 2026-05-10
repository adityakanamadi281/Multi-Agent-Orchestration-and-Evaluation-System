import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.responses import ErrorResponse, ReevalRequest, ReevalResponse

router = APIRouter(tags=["Evaluation"])


@router.post("/re-eval")
async def trigger_reeval(
    request: ReevalRequest,
    db: AsyncSession = Depends(get_db),
):
    from arq import create_pool
    from arq.connections import RedisSettings
    from core.config import settings

    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    reeval_job_id = str(_uuid.uuid4())
    await arq_pool.enqueue_job(
        "run_targeted_reeval",
        test_case_ids=request.test_case_ids,
        rewrite_ids=request.approved_rewrite_ids,
    )
    await arq_pool.close()

    return ReevalResponse(
        reeval_job_id=reeval_job_id,
        test_cases=len(request.test_case_ids),
        status="queued",
    )

