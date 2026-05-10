import json
from core.llm import llm_call
from schemas.tool_result import ToolResult
from schemas.context import AgentOutput

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
                            "span_start": {"type": "integer"},
                            "span_end": {"type": "integer"},
                            "claim_text": {"type": "string"},
                            "confidence": {"type": "number"},
                            "disagreement": {"type": "string"},
                            "source_agent": {"type": "string"},
                        },
                        "required": [
                            "span_start", "span_end", "claim_text",
                            "confidence", "source_agent",
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
report span_start, span_end (character offsets), claim_text, confidence (0.0-1.0),
disagreement (None if accepted, or a string explaining the issue), and source_agent.
Only report genuine contradictions, not stylistic differences."""


class SelfReflectionTool:
    name = "self_reflection"

    async def execute(self, input: dict) -> ToolResult:
        focus = input.get("focus", "")
        context = input.get("context", {})

        outputs_summary = []
        agent_outputs = context.get("agent_outputs", {})
        for aid, ao in agent_outputs.items():
            output_text = ao.output if hasattr(ao, "output") else str(ao)
            outputs_summary.append(f"[{aid}]: {output_text}")

        tool_summary = []
        tool_call_log = context.get("tool_call_log", [])
        for tc in tool_call_log:
            tool_name = tc.tool_name if hasattr(tc, "tool_name") else "?"
            tool_output = tc.output if hasattr(tc, "output") else {}
            tool_summary.append(
                f"Tool '{tool_name}': {json.dumps(tool_output)[:500]}"
            )

        combined = (
            f"Focus: {focus}\n\n"
            + "Agent outputs:\n"
            + "\n---\n".join(outputs_summary)
            + "\n\n"
            + "Tool call results:\n"
            + "\n".join(tool_summary)
        )

        response = await llm_call(
            messages=[
                {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": combined},
            ],
            tools=[REFLECTION_TOOL],
            tool_choice="required",
        )

        args = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )

        return ToolResult(
            status="ok",
            payload={"contradictions": args.get("contradictions", [])},
            latency_ms=0.0,
            retry_count=0,
        )