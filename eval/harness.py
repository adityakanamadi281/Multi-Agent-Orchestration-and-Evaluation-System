import asyncio
import uuid as _uuid
from datetime import datetime, UTC
from agents.graph import compiled_graph
from agents.prompts import AGENT_PROMPTS
from schemas.context import SharedContext
from schemas.eval import TestCase
from eval.scoring import (
    score_answer_correctness,
    score_budget_compliance,
    score_citation_accuracy,
    score_contradiction_resolution,
    score_critique_agreement,
    score_tool_efficiency,
)
from eval.test_cases import TEST_CASES


class EvalHarness:
    def __init__(self):
        self.run_group_id = str(_uuid.uuid4())

    async def run_all(self) -> list:
        results = []
        for tc in TEST_CASES:
            result = await self._run_one(tc)
            results.append(result)
        return results

    async def _run_one(self, tc: TestCase):
        from db import AsyncSessionLocal
        from db.models import EvalRun, EvalCase
        from db.queries import get_agent_events, create_job

        job_id = str(_uuid.uuid4())
        initial = SharedContext(job_id=job_id, original_query=tc.query)

        async with AsyncSessionLocal() as session:
            await create_job(session, _uuid.UUID(job_id), tc.query)

        try:
            final_state_raw = await compiled_graph.ainvoke(
                initial.model_dump() if hasattr(initial, "model_dump")
                else {"job_id": initial.job_id, "original_query": initial.original_query}
            )
            ctx = SharedContext(**final_state_raw) if isinstance(final_state_raw, dict) else final_state_raw
        except Exception as e:
            ctx = initial
            ctx.final_answer = f"[Pipeline error: {e}]"

        final_answer = ctx.final_answer or ""

        async with AsyncSessionLocal() as session:
            events = await get_agent_events(session, _uuid.UUID(job_id))

        correctness = await score_answer_correctness(final_answer, tc)
        citation = await score_citation_accuracy(ctx.agent_outputs)
        contradiction = score_contradiction_resolution(ctx.critique_results, final_answer)
        efficiency = score_tool_efficiency(list(ctx.tool_call_log))
        budget = score_budget_compliance(events)
        agreement = score_critique_agreement(ctx.critique_results, final_answer)

        scores = {
            "answer_correctness": {"score": correctness.score, "justification": correctness.justification},
            "citation_accuracy": {"score": citation.score, "justification": citation.justification},
            "contradiction_resolution": {"score": contradiction.score, "justification": contradiction.justification},
            "tool_efficiency": {"score": efficiency.score, "justification": efficiency.justification},
            "budget_compliance": {"score": budget.score, "justification": budget.justification},
            "critique_agreement": {"score": agreement.score, "justification": agreement.justification},
        }

        prompt_snapshot = {k: v for k, v in AGENT_PROMPTS.items()}

        tool_calls_snapshot = [
            tc.model_dump() if hasattr(tc, "model_dump") else tc
            for tc in ctx.tool_call_log
        ]

        agent_outputs_snapshot = {
            k: v.model_dump() if hasattr(v, "model_dump") else v
            for k, v in ctx.agent_outputs.items()
        }

        eval_run = EvalRun(
            run_group_id=_uuid.UUID(self.run_group_id),
            agent_prompts=prompt_snapshot,
            test_case_id=tc.id,
            category=tc.category,
            query=tc.query,
            final_answer=final_answer,
            scores=scores,
            tool_calls={"calls": tool_calls_snapshot},
            job_id=_uuid.UUID(job_id),
        )

        eval_cases = []
        for dim, sd in scores.items():
            eval_cases.append(EvalCase(
                eval_run_id=eval_run.id,
                dimension=dim,
                score=sd.get("score", 0.0) if isinstance(sd, dict) else float(sd),
                justification=sd.get("justification", "") if isinstance(sd, dict) else "",
            ))

        async with AsyncSessionLocal() as session:
            session.add(eval_run)
            await session.flush()
            for ec in eval_cases:
                ec.eval_run_id = eval_run.id
                session.add(ec)
            await session.commit()
            await session.refresh(eval_run)

        return eval_run