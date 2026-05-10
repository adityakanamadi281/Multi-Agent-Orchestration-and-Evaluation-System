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


async def synthesis_node(state: SharedContext) -> dict:
    agent_id = "synthesis"
    job_id = state.job_id

    await budget_manager.declare_budget(agent_id, MAX_TOKENS)

    flagged_spans = [
        {"span": c.span, "reason": c.reason, "source_agent": c.source_agent}
        for c in state.critique_results
        if c.flagged
    ]

    outputs_summary = {}
    for aid, ao in state.agent_outputs.items():
        outputs_summary[aid] = {
            "output": ao.output,
            "citations": ao.citations,
        }

    client = get_client()

    try:
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[SYNTHESIS_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": AGENT_PROMPTS["synthesis"]},
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

        if not response.choices[0].message.tool_calls:
            raise ValueError(f"Model {settings.MODEL_NAME} failed to return tool calls for synthesis.")

        args = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )
        await budget_manager.consume(agent_id, json.dumps(args))
    except Exception as e:
        logger.error("synthesis_llm_failed", agent_id=agent_id, error=str(e))
        return {
            "routing_log": [{
                "next": "END",
                "reason": f"Synthesis failed: {e}. Check model '{settings.MODEL_NAME}'.",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def _write_event():
        from db.queries import write_agent_event
        from db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            from db.models import Job
            from sqlalchemy import update
            from db.queries import sha256_hex
            await write_agent_event(
                session=session,
                job_id=uuid.UUID(job_id),
                agent_id=agent_id,
                event_type="agent_done",
                input_hash=sha256_hex(list(outputs_summary.keys())),
                output_hash=sha256_hex(args.get("final_answer", "")),
                payload=args,
            )
            await session.execute(
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(final_answer=args.get("final_answer", ""))
            )
            await session.commit()

    asyncio.create_task(_write_event())

    return {
        "final_answer": args.get("final_answer"),
        "provenance_map": args.get("provenance_map", {}),
        "routing_log": [{
            "next": "END",
            "reason": f"Synthesis complete with {len(resolved_spans)} contradictions resolved",
            "agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }





