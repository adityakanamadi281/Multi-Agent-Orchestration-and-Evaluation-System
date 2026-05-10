from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.responses import DimensionStats, ErrorResponse, EvalSummaryResponse
from db.queries import get_latest_eval_runs, get_pending_rewrites

router = APIRouter(tags=["Evaluation"])

DIMENSIONS = [
    "answer_correctness",
    "citation_accuracy",
    "contradiction_resolution",
    "tool_efficiency",
    "budget_compliance",
    "critique_agreement",
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
            pending_rewrites=0,
        )

    run_group_id = str(runs[0].run_group_id)
    timestamp = runs[0].timestamp.isoformat() if runs[0].timestamp else None

    by_cat = defaultdict(lambda: defaultdict(list))
    for run in runs:
        for dim in DIMENSIONS:
            sd = (run.scores or {}).get(dim, {})
            score = sd.get("score", 0.0) if isinstance(sd, dict) else float(sd)
            by_cat[run.category][dim].append(score)

    by_category = {}
    for cat, dims in by_cat.items():
        by_category[cat] = {
            "count": len(runs),
            "avg_scores": {
                dim: round(sum(scores) / len(scores), 3)
                for dim, scores in dims.items()
            },
        }

    by_dim = defaultdict(list)
    for run in runs:
        for dim in DIMENSIONS:
            sd = (run.scores or {}).get(dim, {})
            score = sd.get("score", 0.0) if isinstance(sd, dict) else float(sd)
            by_dim[dim].append(score)

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

