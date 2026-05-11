import json
import asyncio
import time
from datetime import datetime, timezone
from context_manager import get_manager
from context_manager.budget import BudgetExceededException
from core.llm import llm_call
from core.logging import get_logger
from schemas.context import SharedContext, AgentOutput
from agents.prompts import AGENT_PROMPTS
from agents.rag_chunks import RAG_TOOL, _get_knowledge_chunks
from agents.router import log_routing_decision, log_agent_done
from tools.web_search import WebSearchTool

logger = get_logger(__name__)

MAX_BUDGET = 4000


async def run(state: SharedContext) -> dict:
    job_id = state.job_id
    agent_id = "rag_node"
    mgr = await get_manager(job_id)
    await mgr.declare_budget(agent_id, MAX_BUDGET)

    try:
        search_tool = WebSearchTool()

        chunks = _get_knowledge_chunks()
        chunk_context = "\n\n".join(
            f"[{c['id']}] {c['text']}" for c in chunks
        )

        web_result = await search_tool.search(state.original_query, num_results=5)

        combined_context = chunk_context
        if web_result.status == "ok" and web_result.payload:
            web_results = web_result.payload.get("results", [])
            if web_results:
                web_text = "\n\n".join(
                    f"[WEB] {r.get('title', '')}: {r.get('content', '')[:300]}"
                    for r in web_results[:3]
                )
                combined_context += "\n\n" + web_text

        prompt = AGENT_PROMPTS.get(agent_id, "")
        start_time = time.perf_counter()
        response = await llm_call(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Query: {state.original_query}\n\nKnowledge:\n{combined_context}"},
            ],
            tools=[RAG_TOOL],
            tool_choice="required",
        )
        latency_ms = (time.perf_counter() - start_time) * 1000
        token_count = response.usage.total_tokens if hasattr(response, "usage") else 0

        if not response.choices[0].message.tool_calls:
            return {
                "routing_log": [{
                    "from_node": agent_id,
                    "to_node": "critique_node",
                    "reasoning": "RAG LLM failed — no tool calls returned",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        args = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        answer = args.get("answer", "")
        citations_raw = args.get("citations", [])

        citations = [
            {
                "chunk_id": c.get("chunk_id", ""),
                "chunk_text": c.get("chunk_text", ""),
                "hop_number": c.get("hop_number", 1),
            }
            for c in citations_raw
        ]

        reasoning = f"RAG produced answer with {len(citations)} citations"
        routing_entry = {
            "from_node": agent_id,
            "to_node": "critique_node",
            "reasoning": reasoning,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "token_count": token_count,
        }
        
        from db.queries import sha256_hex
        await log_agent_done(
            state=state,
            agent_id=agent_id,
            output_hash=sha256_hex(answer),
            payload=args,
            latency_ms=latency_ms,
            token_count=token_count
        )
        await log_routing_decision(state, agent_id, "critique_node", reasoning, latency_ms=latency_ms, token_count=token_count)

        return {
            "agent_outputs": {
                agent_id: AgentOutput(
                    agent_id=agent_id,
                    output=answer,
                    citations=citations,
                    latency_ms=latency_ms,
                    token_count=token_count,
                )
            },
            "routing_log": [routing_entry],
            "tool_call_log": [{
                "tool_name": "web_search",
                "agent_id": agent_id,
                "input": {"query": state.original_query},
                "output": web_result.payload or {},
                "status": web_result.status,
                "latency_ms": web_result.latency_ms,
                "retry_number": web_result.retry_count,
                "accepted": web_result.status == "ok",
            }],
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