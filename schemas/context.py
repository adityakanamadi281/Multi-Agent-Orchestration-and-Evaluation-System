from __future__ import annotations
import operator
import uuid
from typing import Annotated, Optional
from pydantic import BaseModel, Field


class SubTask(BaseModel):
    id: str
    description: str
    type: str = "factual"
    depends_on: list[str] = []
    status: str = "pending"
    result: Optional[str] = None


class CritiquedClaim(BaseModel):
    span_start: int
    span_end: int
    claim_text: str
    confidence: float
    disagreement: Optional[str] = None
    source_agent: str


class AgentOutput(BaseModel):
    agent_id: str
    output: str
    citations: list[dict] = []
    metadata: dict = Field(default_factory=dict)
    latency_ms: float = 0.0
    token_count: int = 0


class ToolCall(BaseModel):
    tool_name: str
    agent_id: str
    input: dict
    output: dict = {}
    status: str = "ok"
    latency_ms: float = 0.0
    retry_number: int = 0
    accepted: bool = True


class RoutingEntry(BaseModel):
    from_node: str
    to_node: str
    reasoning: str
    timestamp: str
    latency_ms: float = 0.0
    token_count: int = 0


class SharedContext(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_query: str = ""

    sub_tasks: list[SubTask] = []
    agent_outputs: dict[str, AgentOutput] = {}
    critique_results: Annotated[list[CritiquedClaim], operator.add] = []
    final_answer: Optional[str] = None
    provenance_map: dict = {}

    tool_call_log: Annotated[list[ToolCall], operator.add] = []
    routing_log: Annotated[list[RoutingEntry], operator.add] = []

    budget_state: dict = {}
    compression_triggered: bool = False