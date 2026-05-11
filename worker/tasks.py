import json
import uuid as _uuid
from datetime import datetime, UTC
from arq.connections import RedisSettings
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


async def process_query_job(ctx, job_id: str, query: str):
    import redis.asyncio as aioredis
    from agents.graph import compiled_graph
    from schemas.context import SharedContext
    from db.queries import update_job_status
    from db import AsyncSessionLocal
    from context_manager import get_manager, release_manager

    mgr = await get_manager(job_id)
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
                    await publish("agent_done", node_name, {
                        "final_answer": final_answer,
                        "latency_ms": state_update.get("latency_ms", 0.0),
                        "token_count": state_update.get("token_count", 0),
                    })
                elif "agent_outputs" in state_update:
                    for aid, output in state_update["agent_outputs"].items():
                        out_data = output.model_dump() if hasattr(output, "model_dump") else output
                        await publish("agent_done", aid, out_data)
                else:
                    await publish("agent_start", node_name, {"node": node_name})

                if "routing_log" in state_update:
                    for entry in (state_update["routing_log"] or []):
                        if isinstance(entry, dict):
                            # Ensure entry has latency and tokens if they were passed in state_update but not in entry
                            if "latency_ms" not in entry and "latency_ms" in state_update:
                                entry["latency_ms"] = state_update["latency_ms"]
                            if "token_count" not in entry and "token_count" in state_update:
                                entry["token_count"] = state_update["token_count"]
                            await publish("graph_edge", "orchestrator", entry)

        async with AsyncSessionLocal() as session:
            if final_answer is not None:
                await update_job_status(
                    session, _uuid.UUID(job_id), "done",
                    final_answer=final_answer,
                    completed_at=datetime.now(UTC),
                )
                await publish("job_done", "orchestrator", {
                    "final_answer": final_answer,
                })
            else:
                # If we finished but no final_answer was set, something went wrong in the nodes
                await update_job_status(session, _uuid.UUID(job_id), "failed")
                await publish("job_failed", "orchestrator", {"error": "Graph completed without producing a final answer."})

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
        await release_manager(job_id)


async def run_eval_harness(ctx):
    from eval.harness import EvalHarness
    harness = EvalHarness()
    results = await harness.run_all()
    logger.info("eval_harness_complete", run_group_id=harness.run_group_id, cases=len(results))
    return harness.run_group_id


async def run_targeted_reeval(ctx, test_case_ids: list[str], rewrite_ids: list[str]):
    import copy
    from agents.prompts import AGENT_PROMPTS
    from db.queries import get_rewrite_by_id
    from db import AsyncSessionLocal
    from eval.harness import EvalHarness
    from eval.test_cases import TEST_CASES

    original_prompts = copy.deepcopy(AGENT_PROMPTS)

    if rewrite_ids:
        for rid in rewrite_ids:
            try:
                uid = _uuid.UUID(rid)
                async with AsyncSessionLocal() as session:
                    rewrite = await get_rewrite_by_id(session, uid)
                if rewrite and rewrite.agent_id in AGENT_PROMPTS:
                    AGENT_PROMPTS[rewrite.agent_id] = rewrite.new_prompt
            except ValueError:
                logger.warning("invalid_rewrite_id_skipped", rewrite_id=rid)
                continue

    target_cases = [tc for tc in TEST_CASES if not test_case_ids or tc.id in test_case_ids]
    harness = EvalHarness()

    for tc in target_cases:
        await harness._run_one(tc)

    AGENT_PROMPTS.clear()
    AGENT_PROMPTS.update(original_prompts)

    logger.info("targeted_reeval_complete", run_group_id=harness.run_group_id, cases=len(target_cases))
    return str(harness.run_group_id)


class WorkerSettings:
    functions = [process_query_job, run_eval_harness, run_targeted_reeval]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 1200
