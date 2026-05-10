import operator
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class SubTask(BaseModel):
    id: str
    description: str
    type: Literal["research", "code", "analysis", "synthesis"]
    depends_on: list[str] = []
    status: Literal["pending", "running", "done", "blocked"] = "pending"
    result: str | None = None


class CritiquedClaim(BaseModel):
    span: str
    source_agent: str
    confidence: float
    flagged: bool
    reason: str


class AgentOutput(BaseModel):
    agent_id: str
    output: str
    token_count: int
    citations: list[dict] = []
    timestamp: datetime


class ToolCall(BaseModel):
    tool_name: str
    input: dict
    output: dict | None = None
    latency_ms: int = 0
    accepted: bool | None = None
    retry_number: int = 0
    error_code: str | None = None


class SharedContext(BaseModel):
    """
    LangGraph StateGraph state.
    Append-only fields use Annotated[list, operator.add]:
      nodes return only NEW items — the graph merges them.
    All other fields are replaced by whatever the node returns.
    Never mutate state in place inside a node.
    """

    job_id: str
    original_query: str
    sub_tasks: list[SubTask] = []
    agent_outputs: dict[str, AgentOutput] = {}
    context_budget: dict[str, dict] = {}
    final_answer: str | None = None
    provenance_map: dict[str, dict] = {}

    # Append-only — reducer concatenates lists across nodes
    tool_call_log: Annotated[list[ToolCall], operator.add] = []
    critique_results: Annotated[list[CritiquedClaim], operator.add] = []
    routing_log: Annotated[list[dict], operator.add] = []


