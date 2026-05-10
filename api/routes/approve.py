import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.responses import ApproveRequest, ApproveResponse, ErrorResponse
from db.queries import get_rewrite_by_id, approve_rewrite, reject_rewrite

router = APIRouter(tags=["Self-Improving Loop"])


@router.post("/approve/{rewrite_id}")
async def approve_rewrite_endpoint(
    rewrite_id: str,
    request: ApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        rewrite_uuid = uuid.UUID(rewrite_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_REWRITE_ID",
                message=f"'{rewrite_id}' is not a valid UUID.",
                job_id=None,
            ).model_dump(),
        )

    rewrite = await get_rewrite_by_id(db, rewrite_uuid)
    if not rewrite:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code="REWRITE_NOT_FOUND",
                message=f"No prompt rewrite found with ID {rewrite_id}.",
                job_id=None,
            ).model_dump(),
        )

    if rewrite.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                error_code="REWRITE_ALREADY_DECIDED",
                message=(
                    f"Rewrite {rewrite_id} already has status "
                    f"'{rewrite.status}' and cannot be changed."
                ),
                job_id=None,
            ).model_dump(),
        )

    if request.decision == "approved":
        result = await approve_rewrite(db, rewrite_uuid, request.decided_by)
    else:
        result = await reject_rewrite(db, rewrite_uuid, request.decided_by)

    return ApproveResponse(
        rewrite_id=rewrite_id,
        status=request.decision,
        decided_at=result.decided_at.isoformat() if result and result.decided_at else None,
    )

