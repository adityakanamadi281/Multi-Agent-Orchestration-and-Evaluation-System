import asyncio
import sys
import tempfile
import time
from pathlib import Path
from tools.base import BaseTool
from schemas.tool_result import ToolResult, ErrorCode


class CodeSandboxTool(BaseTool):
    name = "code_sandbox"

    async def _execute(self, input: dict) -> ToolResult:
        code = input.get("code", "").strip()
        timeout = float(input.get("timeout_seconds", 10.0))

        if not code:
            return ToolResult(
                success=False,
                error_code=ErrorCode.MALFORMED,
                error_message="code must be non-empty",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "script.py"
            script.write_text(code, encoding="utf-8")
            start = time.monotonic()
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                elapsed = int((time.monotonic() - start) * 1000)
                return ToolResult(
                    success=True,
                    data={
                        "stdout": stdout.decode(errors="replace"),
                        "stderr": stderr.decode(errors="replace"),
                        "exit_code": proc.returncode,
                        "execution_time_ms": elapsed,
                    },
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    error_code=ErrorCode.TIMEOUT,
                    error_message="code execution timed out",
                    data={
                        "stdout": "",
                        "stderr": "timeout",
                        "exit_code": -1,
                    },
                )

