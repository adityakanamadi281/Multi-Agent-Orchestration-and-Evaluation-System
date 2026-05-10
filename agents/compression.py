from core.config import settings
import json
import uuid
import asyncio
from datetime import datetime, timezone
from core.llm import get_client
from core.logging import logger
from context_manager import budget_manager
from schemas.context import SharedContext
from agents.prompts import AGENT_PROMPTS

COMPRESSION_TOOL = {
    "type": "function",
    "function": {
        "name": "compress_routing_log",
        "description": "Compress routing log entries while preserving structured facts",
        "parameters": {
            "type": "object",
            "properties": {
                "compressed_entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "next": {"type": "string"},
                            "reason": {"type": "string"},
                            "agent": {"type": "string"},
                            "timestamp": {"type": "string"},
                        },
                        "required": ["next", "reason", "agent", "timestamp"],
                    },
                },
                "token_reduction_pct": {
                    "type": "number",
                    "description": "Percentage of tokens saved",
                },
            },
            "required": ["compressed_entries", "token_reduction_pct"],
        },
    },
}

MAX_TOKENS = 4000


async def compression_node(state: SharedContext) -> dict:
    agent_id = "compression"
    job_id = state.job_id

    await budget_manager.declare_budget(agent_id, MAX_TOKENS)

    overflowing_agents = [
        entry.get("agent", "unknown")
        for entry in state.routing_log
        if entry.get("next") == "compression_node"
    ]
    overflowing_agent = overflowing_agents[-1] if overflowing_agents else "rag_node"

    lossless_data = []
    for tc in state.tool_call_log:
        lossless_data.append({
            "tool_name": tc.tool_name,
            "input": tc.input,
            "output": tc.output,
        })

    routing_log_json = json.dumps(
        [{"next": r.get("next"), "reason": r.get("reason", ""),
          "agent": r.get("agent", ""), "timestamp": r.get("timestamp", "")}
         for r in state.routing_log]
    )

    client = get_client()

    try:
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,  
            tools=[COMPRESSION_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": AGENT_PROMPTS["compression"]},
                {
                    "role": "user",
                    "content": (
                        f"Routing log to compress:\n{routing_log_json}\n\n"
                        f"Lossless data (preserve verbatim):\n{json.dumps(lossless_data, indent=2)[:2000]}"
                    ),
                },
            ],
        )
    except Exception as e:
        logger.error("compression_llm_failed", agent_id=agent_id, error=str(e))
        return {
            "routing_log": [{
                "next": "rag_node",
                "reason": f"Compression failed, proceeding without compression: {e}",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }

    args = json.loads(
        response.choices[0].message.tool_calls[0].function.arguments
    )
    compressed = args.get("compressed_entries", [])

    await budget_manager.declare_budget(overflowing_agent, MAX_TOKENS)

    async def _write_event():
        from db.queries import write_agent_event
        from db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            from db.queries import sha256_hex
            await write_agent_event(
                session=session,
                job_id=uuid.UUID(job_id),
                agent_id=agent_id,
                event_type="agent_done",
                input_hash=sha256_hex({"overflowing_agent": overflowing_agent}),
                output_hash=sha256_hex({"compressed_count": len(compressed)}),
                payload={
                    "overflowing_agent": overflowing_agent,
                    "compressed_entries": compressed,
                    "token_reduction_pct": args.get("token_reduction_pct", 0),
                },
            )

    asyncio.create_task(_write_event())

    new_budgets = await budget_manager.get_all_budgets()

    return {
        "context_budget": new_budgets,
        "routing_log": compressed + [{
            "next": "rag_node",
            "reason": (
                f"Compressed routing_log for {overflowing_agent}, "
                f"reduced {args.get('token_reduction_pct', 0):.0f}%"
            ),
            "agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }




