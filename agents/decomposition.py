from core.config import settings
import json
import uuid
import asyncio
from datetime import datetime, timezone
from core.llm import get_client
from core.logging import logger
from schemas.context import SharedContext, SubTask
from context_manager import budget_manager
from agents.prompts import AGENT_PROMPTS

DECOMPOSITION_TOOL = {
    "type": "function",
    "function": {
        "name": "decompose_query",
        "description": "Break the query into typed sub-tasks with dependency structure",
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
                            "type": {
                                "type": "string",
                                "enum": ["research", "code", "analysis", "synthesis"],
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["id", "description", "type", "depends_on"],
                    },
                },
            },
            "required": ["sub_tasks"],
        },
    },
}

MAX_TOKENS = 4000


def _topological_sort(sub_tasks: list[dict]) -> None:
    graph = {t["id"]: set(t.get("depends_on", [])) for t in sub_tasks}
    visited = set()
    stack = set()

    def dfs(node: str):
        stack.add(node)
        for dep in graph.get(node, set()):
            if dep in stack:
                raise ValueError(f"Circular dependency detected: {dep}")
            if dep not in visited:
                dfs(dep)
        stack.discard(node)
        visited.add(node)

    for node in graph:
        if node not in visited:
            dfs(node)


async def decomposition_node(state: SharedContext) -> dict:
    agent_id = "decomposition"
    job_id = state.job_id

    try:
        await budget_manager.declare_budget(agent_id, MAX_TOKENS)
    except Exception:
        pass

    client = get_client()
    messages = [
        {"role": "system", "content": AGENT_PROMPTS["decomposition"]},
        {
            "role": "user",
            "content": f"Original query: {state.original_query}\n\nBreak this down into sub-tasks.",
        },
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[DECOMPOSITION_TOOL],
            tool_choice="required",
            messages=messages,
            max_tokens=MAX_TOKENS,
        )

        if not response.choices[0].message.tool_calls:
            raise ValueError(f"Model {settings.MODEL_NAME} failed to return tool calls for decomposition.")

        args = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )
        await budget_manager.consume(agent_id, json.dumps(args))
    except Exception as e:
        logger.error("decomposition_llm_error", error=str(e), job_id=job_id)
        # Fallback: Create a single research task so the pipeline can continue
        args = {
            "sub_tasks": [
                {
                    "id": "t1",
                    "description": f"Research and answer: {state.original_query}",
                    "type": "research",
                    "depends_on": []
                }
            ]
        }
        await budget_manager.consume(agent_id, "fallback_task")
    sub_tasks_raw = args.get("sub_tasks", [])

    try:
        _topological_sort(sub_tasks_raw)
    except ValueError as e:
        logger.warning("dag_cycle_detected", error=str(e), job_id=job_id)

    sub_tasks = [
        SubTask(
            id=t["id"],
            description=t["description"],
            type=t["type"],
            depends_on=t.get("depends_on", []),
            status="pending",
        )
        for t in sub_tasks_raw
    ]

    asyncio.create_task(_log_decomposition_event(job_id, agent_id, sub_tasks))

    return {
        "sub_tasks": sub_tasks,
        "routing_log": [
            {
                "next": "rag_node",
                "reason": f"Decomposed into {len(sub_tasks)} sub-tasks",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


async def _log_decomposition_event(job_id: str, agent_id: str, sub_tasks: list[SubTask]):
    import hashlib
    from db.queries import write_agent_event
    from db import AsyncSessionLocal

    input_data = json.dumps(
        [{"id": t.id, "description": t.description, "type": t.type}
         for t in sub_tasks],
        sort_keys=True,
    )
    input_hash = hashlib.sha256(input_data.encode()).hexdigest()

    async with AsyncSessionLocal() as session:
        await write_agent_event(
            session=session,
            job_id=uuid.UUID(job_id),
            agent_id=agent_id,
            event_type="agent_done",
            input_hash=input_hash,
            token_count=len(sub_tasks),
            payload={"sub_tasks": [t.model_dump() for t in sub_tasks]},
        )





