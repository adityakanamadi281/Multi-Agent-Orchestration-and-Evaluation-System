import json
import uuid
import asyncio
from datetime import datetime, timezone
from context_manager import get_manager
from context_manager.budget import BudgetExceededException
from core.llm import llm_call
from core.logging import get_logger
from schemas.context import SharedContext, SubTask, AgentOutput
from agents.prompts import AGENT_PROMPTS
from agents.router import log_routing_decision

logger = get_logger(__name__)

DECOMPOSITION_TOOL = {
    "type": "function",
    "function": {
        "name": "produce_sub_tasks",
        "description": "Produce sub-tasks from a user query",
        "parameters": {
            "type": "object",
            "properties": {
                "sub_tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "type": {"type": "string"},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "description", "type"],
                    },
                },
            },
            "required": ["sub_tasks"],
        },
    },
}


async def run(state: SharedContext) -> dict:
    job_id = state.job_id
    agent_id = "decomposition_node"
    mgr = await get_manager(job_id)
    await mgr.declare_budget(agent_id, 4000)

    try:
        prompt = AGENT_PROMPTS.get(agent_id, "")
        response = await llm_call(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": state.original_query},
            ],
            tools=[DECOMPOSITION_TOOL],
            tool_choice="required",
        )

        if not response.choices[0].message.tool_calls:
            raise ValueError("Model failed to return tool calls for decomposition.")

        args = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        sub_tasks_raw = args.get("sub_tasks", [])
        sub_tasks = [SubTask(**st) for st in sub_tasks_raw]

        routing_entry = {
            "from_node": agent_id,
            "to_node": "rag_node",
            "reasoning": f"Produced {len(sub_tasks)} sub-tasks",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await log_routing_decision(state, agent_id, "rag_node", f"Produced {len(sub_tasks)} sub-tasks")

        return {
            "sub_tasks": sub_tasks,
            "routing_log": [routing_entry],
            "agent_outputs": {
                agent_id: AgentOutput(
                    agent_id=agent_id,
                    output=json.dumps([st.model_dump() for st in sub_tasks]),
                    citations=[],
                )
            },
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