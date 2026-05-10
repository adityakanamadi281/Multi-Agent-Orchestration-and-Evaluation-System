from core.config import settings
import difflib
import json
import uuid
from datetime import datetime, timezone

from core.llm import get_client
from core.logging import logger
from agents.prompts import AGENT_PROMPTS
from schemas.eval import ScoreResult

META_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_prompt_rewrite",
        "description": "Propose a system prompt improvement based on eval failures",
        "parameters": {
            "type": "object",
            "properties": {
                "new_prompt": {"type": "string"},
                "justification": {"type": "string"},
            },
            "required": ["new_prompt", "justification"],
        },
    },
}

dimension_agent_map = {
    "answer_correctness": "synthesis",
    "citation_accuracy": "rag",
    "contradiction_resolution": "synthesis",
    "tool_efficiency": "decomposition",
    "budget_compliance": "compression",
    "critique_agreement": "critique",
}


class MetaAgent:
    def __init__(self, run_group_id: str):
        self.run_group_id = run_group_id

    async def run(self):
        from db import AsyncSessionLocal
        from db.queries import get_eval_runs_by_group, save_prompt_rewrite

        async with AsyncSessionLocal() as session:
            eval_runs = await get_eval_runs_by_group(
                session, uuid.UUID(self.run_group_id)
            )

        if not eval_runs:
            logger.warning("meta_agent_no_eval_runs", run_group_id=self.run_group_id)
            return None

        dimension_scores: dict[str, list[float]] = {}
        for run in eval_runs:
            if run.scores:
                for dim, score_data in run.scores.items():
                    if isinstance(score_data, dict):
                        score = score_data.get("score", 0.0)
                    elif isinstance(score_data, (int, float)):
                        score = float(score_data)
                    else:
                        continue
                    if dim not in dimension_scores:
                        dimension_scores[dim] = []
                    dimension_scores[dim].append(score)

        if not dimension_scores:
            return None

        worst_dimension = min(
            dimension_scores,
            key=lambda d: sum(dimension_scores[d]) / len(dimension_scores[d]),
        )
        worst_avg = (
            sum(dimension_scores[worst_dimension])
            / len(dimension_scores[worst_dimension])
        )

        worst_agent = dimension_agent_map.get(worst_dimension, "synthesis")
        old_prompt = AGENT_PROMPTS.get(worst_agent, "")

        if not old_prompt:
            return None

        example_failures = [
            {
                "test_case_id": run.test_case_id,
                "category": run.category,
                "query": run.query,
                "scores": run.scores,
            }
            for run in eval_runs
            if run.scores
            and isinstance(run.scores.get(worst_dimension), dict)
            and run.scores[worst_dimension].get("score", 1.0) < 0.5
        ][:3]

        client = get_client()

        try:
            response = await client.chat.completions.create(
                model=settings.MODEL_NAME,  
                tools=[META_TOOL],
                tool_choice="required",
                messages=[
                    {
                        "role": "system",
                        "content": AGENT_PROMPTS["meta"],
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Worst dimension: {worst_dimension} (avg score: {worst_avg:.2f})\n"
                            f"Worst agent: {worst_agent}\n"
                            f"Current prompt:\n{old_prompt}\n\n"
                            f"Example failures:\n{json.dumps(example_failures, indent=2)}"
                        ),
                    },
                ],
            )

            args = json.loads(
                response.choices[0].message.tool_calls[0].function.arguments
            )
        except Exception as e:
            logger.error("meta_agent_llm_failed", error=str(e))
            return None

        new_prompt = args.get("new_prompt", "")
        justification = args.get("justification", "")

        diff = "\n".join(
            difflib.unified_diff(
                old_prompt.splitlines(),
                new_prompt.splitlines(),
                fromfile=f"agents/{worst_agent}/old",
                tofile=f"agents/{worst_agent}/new",
            )
        )

        from db.models import PromptRewrite

        rewrite = PromptRewrite(
            agent_id=worst_agent,
            dimension=worst_dimension,
            old_prompt=old_prompt,
            new_prompt=new_prompt,
            diff=diff,
            justification=justification,
            status="pending",
        )

        async with AsyncSessionLocal() as session:
            saved = await save_prompt_rewrite(session, rewrite)

        logger.info(
            "meta_agent_rewrite_proposed",
            agent_id=worst_agent,
            dimension=worst_dimension,
            avg_score=worst_avg,
            rewrite_id=str(saved.id),
        )

        return saved




