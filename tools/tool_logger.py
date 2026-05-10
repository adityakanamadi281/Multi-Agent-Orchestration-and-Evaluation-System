import asyncio
import hashlib
import json
import time
import uuid
from schemas.tool_result import ToolResult


def logged_tool(tool_instance, job_id: str, agent_id: str):
    async def call(input: dict, retry_number: int = 0) -> ToolResult:
        input_hash = hashlib.sha256(
            json.dumps(input, sort_keys=True).encode()
        ).hexdigest()
        start = time.monotonic()
        result = await tool_instance.execute(input)
        latency_ms = int((time.monotonic() - start) * 1000)

        async def _write_log():
            from db.queries import write_tool_call_log
            from db import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                await write_tool_call_log(
                    session=session,
                    job_id=uuid.UUID(job_id),
                    agent_id=agent_id,
                    tool_name=tool_instance.name,
                    input=input,
                    output=result.payload or {},
                    latency_ms=latency_ms,
                    accepted=result.status == "ok",
                    retry_number=retry_number,
                )

        asyncio.create_task(_write_log())
        return result

    return call