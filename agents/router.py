import asyncio
import json
import uuid
from datetime import datetime, UTC
from langgraph.graph import END
from core.llm import llm_call
from schemas.context import SharedContext, RoutingEntry


ORCHESTRATOR_SYSTEM_PROMPT = """You are the Orchestrator Router for a multi-agent LLM pipeline.

Routing rules (checked in order):
1. compression_node -> rag_node (always re-enter RAG after compression)
2. decomposition_node -> rag_node (sub_tasks exist, rag not yet done)
3. rag_node -> critique_node (rag output exists, critique not yet done)
4. critique_node -> synthesis_node (critique done, synthesis not yet done)
5. synthesis_node -> END (final_answer populated)
6. Any node -> compression_node (if BudgetExceededException in routing_log)

Fallback: use LLM if rules are ambiguous. Return only the next node name."""


async def orchestrator_router(state: SharedContext) -> str:
    routing_log = state.routing_log
    job_id = state.job_id

    if routing_log and routing_log[-1].to_node == "compression_node":
        return "rag_node"

    if not state.sub_tasks and not state.final_answer:
        return "rag_node"

    if state.agent_outputs and "rag_node" in state.agent_outputs and not state.final_answer:
        if state.critique_results or "critique_node" in str(state.agent_outputs.keys()):
            return "synthesis_node"
        return "critique_node"

    if state.critique_results and not state.final_answer:
        return "synthesis_node"

    if state.final_answer:
        return END

    return "rag_node"


async def log_routing_decision(state: SharedContext, from_node: str, to_node: str, reasoning: str, latency_ms: float = 0.0, token_count: int = 0):
    entry = RoutingEntry(
        from_node=from_node,
        to_node=to_node,
        reasoning=reasoning,
        timestamp=datetime.now(UTC).isoformat(),
    )
    async def _write():
        from db.queries import write_agent_event, sha256_hex
        from db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await write_agent_event(
                session=session,
                job_id=uuid.UUID(state.job_id),
                agent_id="orchestrator",
                event_type="graph_edge",
                input_hash=sha256_hex({"from": from_node, "to": to_node}),
                output_hash=sha256_hex({"reasoning": reasoning}),
                latency_ms=latency_ms,
                token_count=token_count,
                payload={"from_node": from_node, "to_node": to_node, "reasoning": reasoning},
            )
    asyncio.create_task(_write())


async def log_agent_done(state: SharedContext, agent_id: str, output_hash: str, payload: dict, latency_ms: float = 0.0, token_count: int = 0, input_hash: str | None = None):
    async def _write():
        from db.queries import write_agent_event, sha256_hex
        from db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await write_agent_event(
                session=session,
                job_id=uuid.UUID(state.job_id),
                agent_id=agent_id,
                event_type="agent_done",
                input_hash=input_hash or sha256_hex(state.original_query),
                output_hash=output_hash,
                latency_ms=latency_ms,
                token_count=token_count,
                payload=payload,
            )
    asyncio.create_task(_write())