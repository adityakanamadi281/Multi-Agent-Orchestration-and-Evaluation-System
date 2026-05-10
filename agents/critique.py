from core.config import settings
import json
import uuid
import asyncio
from datetime import datetime, timezone
from core.llm import get_client
from core.logging import logger
from context_manager import budget_manager
from schemas.context import SharedContext, CritiquedClaim
from agents.prompts import AGENT_PROMPTS

CRITIQUE_TOOL = {
    "type": "function",
    "function": {
        "name": "evaluate_claims",
        "description": "Evaluate factual claims in an agent's output",
        "parameters": {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "span": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                            "flagged": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["span", "confidence", "flagged", "reason"],
                    },
                },
            },
            "required": ["claims"],
        },
    },
}

MAX_TOKENS = 6000


async def critique_node(state: SharedContext) -> dict:
    agent_id = "critique"
    job_id = state.job_id

    await budget_manager.declare_budget(agent_id, MAX_TOKENS)

    new_claims = []
    client = get_client()

    for output_agent_id, agent_output in state.agent_outputs.items():
        output_text = agent_output.output
        if not output_text:
            continue

        try:
            response = await client.chat.completions.create(
                model=settings.MODEL_NAME,  
                tools=[CRITIQUE_TOOL],
                tool_choice="required",
                messages=[
                    {"role": "system", "content": AGENT_PROMPTS["critique"]},
                    {
                        "role": "user",
                        "content": (
                            f"Review the following output from agent '{output_agent_id}':\n\n"
                            f"{output_text}"
                        ),
                    },
                ],
            )
            
            if not response.choices[0].message.tool_calls:
                logger.error("critique_llm_no_tool_call", agent_id=agent_id, output_agent=output_agent_id)
                continue

            args = json.loads(
                response.choices[0].message.tool_calls[0].function.arguments
            )
            await budget_manager.consume(
                agent_id,
                json.dumps(args),
            )
        except Exception as e:
            logger.error("critique_llm_failed", agent_id=agent_id, error=str(e))
            continue
        raw_claims = args.get("claims", [])

        for claim_dict in raw_claims:
            span = claim_dict.get("span", "")
            if span and span not in output_text:
                logger.warning(
                    "critique_span_not_substring",
                    span=span[:60],
                    agent=output_agent_id,
                )
                continue

            new_claims.append(
                CritiquedClaim(
                    span=span,
                    source_agent=output_agent_id,
                    confidence=float(claim_dict.get("confidence", 0.0)),
                    flagged=bool(claim_dict.get("flagged", False)),
                    reason=claim_dict.get("reason", ""),
                )
            )

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
                input_hash=sha256_hex(list(state.agent_outputs.keys())),
                output_hash=sha256_hex([c.span for c in new_claims]),
                payload={
                    "claims": [c.model_dump() for c in new_claims],
                    "total_flagged": sum(1 for c in new_claims if c.flagged),
                },
            )

    asyncio.create_task(_write_event())

    return {
        "critique_results": new_claims,
        "routing_log": [{
            "next": "synthesis_node",
            "reason": f"Critiqued {len(new_claims)} claims, flagged {sum(1 for c in new_claims if c.flagged)}",
            "agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }




