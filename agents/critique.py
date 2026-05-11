import json
import time
from datetime import datetime, timezone
from context_manager import get_manager
from context_manager.budget import BudgetExceededException
from core.llm import llm_call
from core.logging import get_logger
from schemas.context import SharedContext, CritiquedClaim
from agents.prompts import AGENT_PROMPTS
from agents.router import log_routing_decision, log_agent_done

logger = get_logger(__name__)


CRITIQUE_TOOL = {
    "type": "function",
    "function": {
        "name": "critique_claims",
        "description": "Identify and critique factual claims in agent outputs",
        "parameters": {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "span_start": {"type": "integer"},
                            "span_end": {"type": "integer"},
                            "claim_text": {"type": "string"},
                            "confidence": {"type": "number"},
                            "disagreement": {"type": "string"},
                            "source_agent": {"type": "string"},
                        },
                        "required": ["span_start", "span_end", "claim_text", "confidence", "source_agent"],
                    },
                },
            },
            "required": ["claims"],
        },
    },
}


async def run(state: SharedContext) -> dict:
    job_id = state.job_id
    agent_id = "critique_node"
    mgr = await get_manager(job_id)
    await mgr.declare_budget(agent_id, 4000)

    try:
        outputs_text = ""
        for aid, output in state.agent_outputs.items():
            outputs_text += f"\n\n[{aid}]: {output.output}"

        prompt = AGENT_PROMPTS.get(agent_id, "")
        start_time = time.perf_counter()
        response = await llm_call(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Agent outputs to critique:{outputs_text}"},
            ],
            tools=[CRITIQUE_TOOL],
            tool_choice="required",
        )
        latency_ms = (time.perf_counter() - start_time) * 1000
        token_count = response.usage.total_tokens if hasattr(response, "usage") else 0

        if not response.choices[0].message.tool_calls:
            logger.error("critique_llm_no_tool_call", agent_id=agent_id)
            return {
                "routing_log": [{
                    "from_node": agent_id,
                    "to_node": "synthesis_node",
                    "reasoning": "Critique LLM failed — skipping to synthesis",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        args = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        claims_raw = args.get("claims", [])
        new_claims = [CritiquedClaim(**c) for c in claims_raw]

        reasoning = f"Critiqued {len(new_claims)} claims"
        routing_entry = {
            "from_node": agent_id,
            "to_node": "synthesis_node",
            "reasoning": reasoning,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "token_count": token_count,
        }
        
        from db.queries import sha256_hex
        await log_agent_done(
            state=state,
            agent_id=agent_id,
            output_hash=sha256_hex(args),
            payload=args,
            latency_ms=latency_ms,
            token_count=token_count
        )
        await log_routing_decision(state, agent_id, "synthesis_node", reasoning, latency_ms=latency_ms, token_count=token_count)

        return {
            "critique_results": new_claims,
            "routing_log": [routing_entry],
        }

    except BudgetExceededException as e:
        logger.error("budget_exceeded", agent_id=agent_id, job_id=job_id)
        return {
            "compression_triggered": True,
            "routing_log": [{
                "from_node": agent_id,
                "to_node": "compression_node",
                "reasoning": f"Budget exceeded: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }