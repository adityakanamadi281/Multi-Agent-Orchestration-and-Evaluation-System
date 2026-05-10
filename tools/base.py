import asyncio
import time
from abc import ABC, abstractmethod
from schemas.tool_result import ToolResult, ErrorCode


class BaseTool(ABC):
    name: str = "base_tool"
    timeout_seconds: float = 10.0
    max_retries: int = 2

    @abstractmethod
    async def _execute(self, input: dict) -> ToolResult:
        ...

    async def execute(self, input: dict) -> ToolResult:
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._execute(input),
                timeout=self.timeout_seconds,
            )
            if result.latency_ms == 0:
                result.latency_ms = int((time.monotonic() - start) * 1000)
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error_code=ErrorCode.TIMEOUT,
                error_message=f"{self.name} timed out after {self.timeout_seconds}s",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
                latency_ms=int((time.monotonic() - start) * 1000),
            )

