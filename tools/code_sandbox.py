import asyncio
import os
import tempfile
import time
from schemas.tool_result import ToolResult
from core.config import settings


class CodeSandboxTool:
    async def run(self, code: str, timeout_seconds: int | None = None) -> ToolResult:
        timeout = timeout_seconds or settings.CODE_SANDBOX_TIMEOUT_SEC

        if not code or not code.strip():
            return ToolResult(
                status="malformed",
                payload={"error": "empty code string"},
                latency_ms=0.0,
                retry_count=0,
            )

        start = time.monotonic()
        tmp_path = None
        process = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
                f.write(code)
                tmp_path = f.name

            process = await asyncio.create_subprocess_exec(
                "python",
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                return ToolResult(
                    status="ok",
                    payload={
                        "stdout": stdout.decode(errors="replace"),
                        "stderr": stderr.decode(errors="replace"),
                        "exit_code": process.returncode,
                        "execution_time_ms": (time.monotonic() - start) * 1000,
                    },
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    status="timeout",
                    payload={"error": f"execution exceeded {timeout}s", "exit_code": -1},
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def execute(self, input: dict) -> ToolResult:
        code = input.get("code", "")
        timeout = input.get("timeout_seconds")
        return await self.run(code, timeout)