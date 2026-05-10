import json
import uuid as _uuid
from datetime import datetime, UTC
from arq.connections import RedisSettings
from core.config import settings
from core.logging import logger


async def process_query_job(ctx, job_id: str, query: str):
    import redis.asyncio as aioredis
    from agents.graph import compiled_graph
    from schemas.context import SharedContext
    from db.queries import update_job_status
    from db import AsyncSessionLocal

    r = aioredis.from_url(settings.REDIS_URL)
    channel = f"job:{job_id}"

    async def publish(event_type: str, agent_id: str, data: dict):
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        event = {
            "job_id": job_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await r.publish(channel, json.dumps(event, default=json_serial))

    try:
        async with AsyncSessionLocal() as session:
            await update_job_status(session, _uuid.UUID(job_id), "running")

        await publish("job_started", "orchestrator", {"query": query})

        initial = SharedContext(job_id=job_id, original_query=query)

        final_answer = None
        async for event in compiled_graph.astream(
            initial.model_dump() if hasattr(initial, "model_dump")
            else {"job_id": initial.job_id, "original_query": initial.original_query}
        ):
            for node_name, state_update in event.items():
                if not isinstance(state_update, dict):
                    continue

                if "final_answer" in state_update and state_update["final_answer"]:
                    final_answer = state_update["final_answer"]

                routing_log = state_update.get("routing_log", [])
                for entry in routing_log or []:
                    if isinstance(entry, dict):
                        await publish("graph_edge", "orchestrator", entry)

                if "final_answer" in state_update and state_update["final_answer"]:
                    await publish("agent_done", node_name, {
                        "final_answer": state_update["final_answer"]
                    })
                elif "agent_outputs" in state_update:
                    for aid, output in state_update["agent_outputs"].items():
                        out_data = output.model_dump() if hasattr(output, "model_dump") else output
                        await publish("agent_done", aid, out_data)
                else:
                    await publish("agent_start", node_name, {"node": node_name})

                if "context_budget" in state_update:
                    await publish("budget_update", node_name, state_update["context_budget"])

        async with AsyncSessionLocal() as session:
            await update_job_status(
                session, _uuid.UUID(job_id), "done",
                final_answer=final_answer or "",
                completed_at=datetime.now(UTC),
            )

        await publish("job_done", "orchestrator", {
            "final_answer": final_answer,
        })

    except Exception as e:
        logger.error("job_failed", job_id=job_id, error=str(e))
        try:
            async with AsyncSessionLocal() as session:
                await update_job_status(session, _uuid.UUID(job_id), "failed")
        except Exception:
            pass
        await publish("job_failed", "orchestrator", {"error": str(e)})
        raise
    finally:
        await r.aclose()


async def run_eval_harness(ctx):
    from eval.harness import EvalHarness
    harness = EvalHarness()
    await harness.run_all()
    logger.info("eval_harness_complete", run_group_id=harness.run_group_id)
    return harness.run_group_id


async def run_targeted_reeval(ctx, test_case_ids: list[str], rewrite_ids: list[str]):
    from agents.prompts import AGENT_PROMPTS as original_prompts
    from agents.prompts import AGENT_PROMPTS
    from db.queries import get_rewrite_by_id
    from db import AsyncSessionLocal
    from eval.harness import EvalHarness
    from eval.test_cases import TEST_CASES

    saved_prompts: dict[str, str] = {}

    if rewrite_ids:
        for rid in rewrite_ids:
            async with AsyncSessionLocal() as session:
                rewrite = await get_rewrite_by_id(session, _uuid.UUID(rid))
            if rewrite:
                saved_prompts[rewrite.agent_id] = AGENT_PROMPTS.get(rewrite.agent_id, "")
                AGENT_PROMPTS[rewrite.agent_id] = rewrite.new_prompt

    target_cases = [
        tc for tc in TEST_CASES
        if not test_case_ids or tc.id in test_case_ids
    ]

    harness = EvalHarness()
    original_scores_by_case: dict[str, dict] = {}

    for tc in target_cases:
        eval_run = await harness._run_one(tc)
        if rewrite_ids and eval_run.scores:
            delta = {
                dim: round(v.get("score", 0.0), 3) if isinstance(v, dict) else round(float(v), 3)
                for dim, v in eval_run.scores.items()
            }
            async with AsyncSessionLocal() as session:
                for rid in rewrite_ids:
                    from sqlalchemy import update
                    from db.models import PromptRewrite
                    await session.execute(
                        update(PromptRewrite)
                        .where(PromptRewrite.id == _uuid.UUID(rid))
                        .values(
                            performance_delta=delta,
                            eval_run_id=eval_run.id,
                        )
                    )
                await session.commit()

    for agent_id, old_prompt in saved_prompts.items():
        AGENT_PROMPTS[agent_id] = old_prompt

    logger.info(
        "targeted_reeval_complete",
        run_group_id=harness.run_group_id,
        test_cases_run=len(target_cases),
    )

    return str(harness.run_group_id)


class WorkerSettings:
    functions = [process_query_job, run_eval_harness, run_targeted_reeval]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 600

