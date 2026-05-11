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
from agents.router import log_routing_decision, log_agent_done

SYNTHESIS_TOOL = {
    "type": "function",
    "function": {
        "name": "produce_final_answer",
        "description": "Merge agent outputs into a single coherent final answer",
        "parameters": {
            "type": "object",
            "properties": {
                "final_answer": {
                    "type": "string",
                    "description": "The complete merged answer text",
                },
                "provenance_map": {
                    "type": "object",
                    "description": "Mapping of sentence indices to source agents and chunk IDs",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "agent_id": {"type": "string"},
                            "chunk_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "resolved_contradiction": {"type": "boolean"},
                        },
                        "required": ["agent_id", "chunk_ids", "resolved_contradiction"],
                    },
                },
                "resolved_contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "span": {"type": "string"},
                            "resolution": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["span", "resolution", "reasoning"],
                    },
                },
            },
            "required": ["final_answer", "provenance_map", "resolved_contradictions"],
        },
    },
}

MAX_TOKENS = 8000


async def run(state: SharedContext) -> dict:
    agent_id = "synthesis_node"
    job_id = state.job_id

    mgr = await get_manager(job_id)
    await mgr.declare_budget(agent_id, MAX_TOKENS)

    flagged_spans = [
        {"span": c.claim_text, "reason": c.disagreement, "source_agent": c.source_agent}
        for c in state.critique_results
        if c.disagreement
    ]

    outputs_summary = {}
    for aid, ao in state.agent_outputs.items():
        outputs_summary[aid] = {
            "output": ao.output,
            "citations": ao.citations,
        }

    client = get_client()

    try:
        start_time = time.perf_counter()
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[SYNTHESIS_TOOL],
            tool_choice="auto",
            messages=[
                {"role": "system", "content": AGENT_PROMPTS[agent_id] + "\n\nIMPORTANT: You must use the 'produce_final_answer' tool to provide the structured final answer."},
                {
                    "role": "user",
                    "content": (
                        f"Original query: {state.original_query}\n\n"
                        f"Agent outputs:\n{json.dumps(outputs_summary, indent=2)}\n\n"
                        f"Flagged claims from critique:\n{json.dumps(flagged_spans, indent=2)}\n\n"
                        "Merge these into a single coherent final answer. "
                        "Every flagged claim must be resolved."
                    ),
                },
            ],
            max_tokens=MAX_TOKENS,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000
        token_count = response.usage.total_tokens if hasattr(response, "usage") else 0

        message = response.choices[0].message
        if message.tool_calls:
            args = json.loads(message.tool_calls[0].function.arguments)
        elif message.content:
            args = {
                "final_answer": message.content,
                "provenance_map": {},
                "resolved_contradictions": []
            }
            logger.warning("synthesis_llm_fallback_to_content", agent_id=agent_id, job_id=job_id)
        else:
            raise ValueError(f"Model {settings.MODEL_NAME} returned neither a tool call nor content for synthesis.")

        await mgr.consume(agent_id, json.dumps(args))
    except Exception as e:
        logger.error("synthesis_llm_failed", agent_id=agent_id, error=str(e))
        return {
            "routing_log": [{
                "from_node": agent_id,
                "to_node": "END",
                "reasoning": f"Synthesis failed: {e}. Check model '{settings.MODEL_NAME}'.",
                "timestamp": datetime.now(UTC).isoformat(),
            }]
        }

    resolved_spans = {
        r["span"] for r in args.get("resolved_contradictions", [])
    }
    for flagged in flagged_spans:
        if flagged["span"] not in resolved_spans:
            logger.warning(
                "unresolved_flagged_span",
                span=flagged["span"][:60],
                job_id=job_id,
            )

    from db.queries import sha256_hex
    await log_agent_done(
        state=state,
        agent_id=agent_id,
        output_hash=sha256_hex(args.get("final_answer", "")),
        payload=args,
        latency_ms=latency_ms,
        token_count=token_count
    )

    reasoning = f"Synthesis complete with {len(resolved_spans)} contradictions resolved"
    await log_routing_decision(state, agent_id, "END", reasoning, latency_ms=latency_ms, token_count=token_count)

    # Update job final answer separately as synthesis is the end
    async def _update_job():
        from db import AsyncSessionLocal
        from sqlalchemy import update
        from db.models import Job
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    update(Job)
                    .where(Job.id == uuid.UUID(job_id))
                    .values(final_answer=args.get("final_answer", ""))
                )
                await session.commit()
            except Exception as e:
                logger.warning("failed_to_update_job_final_answer", job_id=job_id, error=str(e))
    asyncio.create_task(_update_job())

    return {
        "final_answer": args.get("final_answer"),
        "provenance_map": args.get("provenance_map", {}),
        "latency_ms": latency_ms,
        "token_count": token_count,
        "routing_log": [{
            "from_node": agent_id,
            "to_node": "END",
            "reasoning": reasoning,
            "timestamp": datetime.now(UTC).isoformat(),
            "latency_ms": latency_ms,
            "token_count": token_count,
        }],
    }