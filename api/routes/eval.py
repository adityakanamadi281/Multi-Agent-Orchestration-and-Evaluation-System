from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_db
from api.schemas.responses import DimensionStats, ErrorResponse, EvalSummaryResponse, ReevalResponse
from db.queries import get_latest_eval_runs, get_pending_rewrites
from arq import create_pool
from arq.connections import RedisSettings
from core.config import settings
import uuid as _uuid

router = APIRouter(tags=["Evaluation"])

DIMENSIONS = [
    "answer_correctness", "citation_accuracy", "contradiction_resolution",
    "tool_efficiency", "budget_compliance", "critique_agreement",
]


@router.get("/eval/latest")
async def get_latest_eval(db: AsyncSession = Depends(get_db)):
    try:
        runs = await get_latest_eval_runs(db)
        pending = await get_pending_rewrites(db)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message=str(exc),
                job_id=None,
            ).model_dump(),
        )

    if not runs:
        return EvalSummaryResponse(
            run_group_id=None,
            timestamp=None,
            total_cases=0,
            by_category={},
            by_dimension={},
            pending_rewrites=len(pending),
        )

    run_group_id = str(runs[0].run_group_id)
    timestamp = runs[0].timestamp.isoformat() if runs[0].timestamp else None

    by_cat = defaultdict(lambda: defaultdict(list))
    by_dim = defaultdict(list)

    for run in runs:
        for dim in DIMENSIONS:
            sd = (run.scores or {}).get(dim, {})
            score = sd.get("score", 0.0) if isinstance(sd, dict) else float(sd)
            by_cat[run.category][dim].append(score)
            by_dim[dim].append(score)

    by_category = {}
    for cat, dims in by_cat.items():
        # Handle potential enum objects as keys
        cat_str = cat.name if hasattr(cat, 'name') else str(cat)
        by_category[cat_str] = {
            "count": len(dims.get("answer_correctness", [])),
            "avg_scores": {
                dim: round(sum(scores) / len(scores), 3)
                for dim, scores in dims.items()
            },
        }

    by_dimension = {}
    for dim, scores in by_dim.items():
        if scores:
            by_dimension[dim] = DimensionStats(
                mean=round(sum(scores) / len(scores), 3),
                min=round(min(scores), 3),
                max=round(max(scores), 3),
            )

    return EvalSummaryResponse(
        run_group_id=run_group_id,
        timestamp=timestamp,
        total_cases=len(runs),
        by_category=by_category,
        by_dimension=by_dimension,
        pending_rewrites=len(pending),
    )


@router.post("/eval/run", response_model=ReevalResponse)
async def trigger_eval():
    """Trigger the full evaluation harness."""
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        job_id = str(_uuid.uuid4())
        await arq_pool.enqueue_job("run_eval_harness", _job_id=job_id)
    finally:
        await arq_pool.close()

    return ReevalResponse(
        reeval_job_id=job_id,
        test_cases=15,  # Standard test suite size
        status="queued",
    )
