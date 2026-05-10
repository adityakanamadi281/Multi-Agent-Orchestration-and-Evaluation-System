from core.config import settings
import json
import asyncio
from datetime import datetime, timezone
from langgraph.graph import END
from core.llm import get_client
from schemas.context import SharedContext

ORCHESTRATOR_SYSTEM_PROMPT = """You are an orchestrator for a multi-agent LLM pipeline.
Examine the current pipeline state and decide which agent to run next.

Routing rules (apply in order):
1. sub_tasks is empty                         -> decomposition_node
2. sub_tasks exist, no rag output             -> rag_node
3. rag output exists, no critique             -> critique_node
4. critique done, no synthesis                -> synthesis_node
5. synthesis done, all contradictions resolved -> END
6. any agent's routing_log says next=compression_node -> compression_node
7. Never route the same node twice in a row unless justified

Return next_agent, reasoning, context_budget_allocation, priority."""

ROUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "route_decision",
        "description": "Decide which agent node runs next",
        "parameters": {
            "type": "object",
            "properties": {
                "next_agent": {
                    "type": "string",
                    "enum": [
                        "decomposition_node",
                        "rag_node",
                        "critique_node",
                        "synthesis_node",
                        "compression_node",
                        "END",
                    ],
                },
                "reasoning": {"type": "string"},
                "context_budget_allocation": {"type": "integer"},
                "priority": {"type": "integer"},
            },
            "required": [
                "next_agent",
                "reasoning",
                "context_budget_allocation",
                "priority",
            ],
        },
    },
}


async def _write_routing_event(job_id: str, decision: dict):
    import uuid
    from db.queries import write_agent_event
    from db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        from db.queries import sha256_hex
        await write_agent_event(
            session=session,
            job_id=uuid.UUID(job_id),
            agent_id="orchestrator",
            event_type="graph_edge",
            input_hash=sha256_hex({"decision": decision}),
            output_hash=None,
            payload=decision,
        )


async def orchestrator_router(state: SharedContext) -> str:
    client = get_client()

    state_data = {
        "job_id": state.job_id,
        "original_query": state.original_query[:200],
        "sub_tasks": [
            {"id": t.id, "status": t.status, "depends_on": t.depends_on}
            for t in state.sub_tasks
        ],
        "agents_completed": list(state.agent_outputs.keys()),
        "critique_count": len(state.critique_results),
        "final_answer_present": state.final_answer is not None,
        "routing_log": [
            {"next": r.get("next"), "agent": r.get("agent")}
            for r in state.routing_log
        ],
    }

    response = await client.chat.completions.create(
        model=settings.MODEL_NAME,  
        tools=[ROUTE_TOOL],
        tool_choice="required",
        messages=[
            {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Pipeline state:\n{json.dumps(state_data, indent=2)}",
            },
        ],
    )

    try:
        decision = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )
        next_node = decision.get("next_agent", "synthesis_node")
    except (json.JSONDecodeError, AttributeError, IndexError, KeyError):
        next_node = "synthesis_node"
        decision = {"next_agent": next_node, "reasoning": "Fallback due to LLM error"}

    asyncio.create_task(
        _write_routing_event(state.job_id, decision)
    )

    return END if next_node == "END" else next_node




