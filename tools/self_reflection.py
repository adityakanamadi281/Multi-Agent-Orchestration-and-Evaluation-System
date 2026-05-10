from core.config import settings
import json
from core.llm import get_client
from tools.base import BaseTool
from schemas.tool_result import ToolResult, ErrorCode

REFLECTION_TOOL = {
    "type": "function",
    "function": {
        "name": "report_contradictions",
        "description": "Report contradictions found in agent outputs",
        "parameters": {
            "type": "object",
            "properties": {
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim_a": {"type": "string"},
                            "claim_b": {"type": "string"},
                            "source_a": {"type": "string"},
                            "source_b": {"type": "string"},
                            "severity": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                        },
                        "required": [
                            "claim_a", "claim_b", "source_a",
                            "source_b", "severity",
                        ],
                    },
                },
            },
            "required": ["contradictions"],
        },
    },
}

REFLECTION_SYSTEM_PROMPT = """You are a contradiction detector. Examine agent outputs
and tool call logs to find factual contradictions. For each pair of conflicting claims,
report both claims, their source agents, and a severity score (0.0 = minor nuance,
1.0 = direct contradiction on core facts). Only report genuine contradictions,
not stylistic differences or paraphrasing."""


class SelfReflectionTool(BaseTool):
    name = "self_reflection"
    timeout_seconds = 30.0

    async def _execute(self, input: dict) -> ToolResult:
        focus = input.get("focus", "")
        context = input.get("context", {})

        outputs_summary = []
        for aid, ao in context.get("agent_outputs", {}).items():
            outputs_summary.append(f"[{aid}]: {ao.get('output', str(ao))}")

        tool_summary = []
        for tc in context.get("tool_call_log", []):
            tool_summary.append(
                f"Tool '{tc.get('tool_name', '?')}': {json.dumps(tc.get('output', {}))[:500]}"
            )

        combined = (
            f"Focus: {focus}\n\n"
            f"Agent outputs:\n" + "\n---\n".join(outputs_summary) + "\n\n"
            f"Tool call results:\n" + "\n".join(tool_summary)
        )

        client = get_client()
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[REFLECTION_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": combined},
            ],
        )

        args = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )

        return ToolResult(
            success=True,
            data={"contradictions": args.get("contradictions", [])},
        )


