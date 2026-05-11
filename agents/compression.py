import asyncio
import json
import uuid
import time
from datetime import UTC, datetime

from agents.prompts import AGENT_PROMPTS
from context_manager import get_manager
from core.config import settings
from core.llm import get_llm_client as get_client
from core.logging import get_logger
logger = get_logger(__name__)
from schemas.context import SharedContext
from agents.router import log_agent_done, log_routing_decision

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
                            "from_node": {"type": "string"},
                            "to_node": {"type": "string"},
                            "reasoning": {"type": "string"},
                            "timestamp": {"type": "string"},
                        },
                        "required": ["from_node", "to_node", "reasoning", "timestamp"],
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


async def run(state: SharedContext) -> dict:
    agent_id = "compression_node"
    job_id = state.job_id

    mgr = await get_manager(job_id)
    await mgr.declare_budget(agent_id, MAX_TOKENS)

    overflowing_agents = [
        entry.from_node
        for entry in state.routing_log
        if entry.to_node == "compression_node"
    ]
    overflowing_agent = overflowing_agents[-1] if overflowing_agents else "rag_node"

    lossless_data = []
    for tc in state.tool_call_log:
        lossless_data.append({
            "tool_name": tc.tool_name,
            "input": tc.input,
            "output": tc.output,
        })

    routing_log_entries = [
        {
            "from_node": r.from_node,
            "to_node": r.to_node,
            "reasoning": r.reasoning,
            "timestamp": r.timestamp,
        }
        for r in state.routing_log
        if hasattr(r, "from_node")
    ]

    client = get_client()

    try:
        start_time = time.perf_counter()
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[COMPRESSION_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": AGENT_PROMPTS[agent_id]},
                {
                    "role": "user",
                    "content": (
                        f"Routing log to compress:\n{json.dumps(routing_log_entries, indent=2)}\n\n"
                        f"Lossless data (preserve verbatim):\n{json.dumps(lossless_data, indent=2)[:2000]}"
                    ),
                },
            ],
        )
        latency_ms = (time.perf_counter() - start_time) * 1000
        token_count = response.usage.total_tokens if hasattr(response, "usage") else 0
    except Exception as e:
        logger.error("compression_llm_failed", agent_id=agent_id, error=str(e))
        return {
            "routing_log": [{
                "from_node": agent_id,
                "to_node": "rag_node",
                "reasoning": f"Compression failed, proceeding without compression: {e}",
                "timestamp": datetime.now(UTC).isoformat(),
            }]
        }

    args = json.loads(
        response.choices[0].message.tool_calls[0].function.arguments
    )
    compressed = args.get("compressed_entries", [])

    from db.queries import sha256_hex
    payload = {
        "overflowing_agent": overflowing_agent,
        "compressed_entries": compressed,
        "token_reduction_pct": args.get("token_reduction_pct", 0),
    }
    await log_agent_done(
        state=state,
        agent_id=agent_id,
        output_hash=sha256_hex({"compressed_count": len(compressed)}),
        payload=payload,
        latency_ms=latency_ms,
        token_count=token_count,
        input_hash=sha256_hex({"overflowing_agent": overflowing_agent})
    )

    reasoning = (
        f"Compressed routing_log for {overflowing_agent}, "
        f"reduced {args.get('token_reduction_pct', 0):.0f}%"
    )
    await log_routing_decision(state, agent_id, "rag_node", reasoning, latency_ms=latency_ms, token_count=token_count)

    return {
        "context_budget": {},
        "routing_log": [{"_replace_all": True}] + compressed + [{
            "from_node": agent_id,
            "to_node": "rag_node",
            "reasoning": reasoning,
            "timestamp": datetime.now(UTC).isoformat(),
        }],
    }