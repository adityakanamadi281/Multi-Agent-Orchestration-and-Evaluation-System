from typing import Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    job_id: str | None = None


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    stream: bool = True


class QueryQueued(BaseModel):
    job_id: str
    status: str = "queued"


class TraceResponse(BaseModel):
    job_id: str
    status: str
    query: str
    final_answer: str | None = None
    agent_events: list[dict] = []
    tool_calls: list[dict] = []
    graph_edges: list[dict] = []
    created_at: str | None = None
    completed_at: str | None = None


class DimensionStats(BaseModel):
    mean: float
    min: float
    max: float


class EvalSummaryResponse(BaseModel):
    run_group_id: str | None = None
    timestamp: str | None = None
    total_cases: int = 0
    by_category: dict[str, Any] = {}
    by_dimension: dict[str, DimensionStats] = {}
    pending_rewrites: int = 0


class ApproveRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    decided_by: str = Field(..., min_length=1)


class ApproveResponse(BaseModel):
    rewrite_id: str
    status: str
    decided_at: str | None = None


class ReevalRequest(BaseModel):
    test_case_ids: list[str] = []
    approved_rewrite_ids: list[str] = []


class ReevalResponse(BaseModel):
    reeval_job_id: str
    test_cases: int = 0
    status: str = "queued"
