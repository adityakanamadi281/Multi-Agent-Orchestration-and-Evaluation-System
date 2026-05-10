import asyncio
import hashlib
import json
import time
from schemas.tool_result import ToolResult


def logged_tool(tool_instance, job_id: str, agent_id: str):
    """
    Returns an async wrapper around tool_instance.execute() that:
    1. Records input_hash before the call
    2. Calls execute()
    3. Records output_hash, latency_ms, and error_code after
    4. Writes ToolCallLog row (fire-and-forget)
    5. Returns the ToolResult unchanged
    """

    async def call(input: dict, retry_number: int = 0) -> ToolResult:
        input_hash = hashlib.sha256(
            json.dumps(input, sort_keys=True).encode()
        ).hexdigest()
        start = time.monotonic()
        result = await tool_instance.execute(input)
        latency_ms = int((time.monotonic() - start) * 1000)
        output_hash = (
            hashlib.sha256(
                json.dumps(result.data, sort_keys=True).encode()
            ).hexdigest()
            if result.data
            else None
        )

        from db.queries import write_tool_call_log
        from db import AsyncSessionLocal

        async def _write_log():
            async with AsyncSessionLocal() as session:
                await write_tool_call_log(
                    session=session,
                    job_id=job_id,
                    agent_id=agent_id,
                    tool_name=tool_instance.name,
                    input=input,
                    output=result.data,
                    latency_ms=latency_ms,
                    accepted=None,
                    retry_number=retry_number,
                )

        asyncio.create_task(_write_log())
        return result

    return call

