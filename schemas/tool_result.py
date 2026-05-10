from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    TIMEOUT = "timeout"
    EMPTY = "empty"
    MALFORMED = "malformed"
    EXECUTION_ERROR = "execution_error"


class ToolResult:
    __slots__ = ("status", "payload", "latency_ms", "retry_count")

    def __init__(
        self,
        status: str,
        payload: Any = None,
        latency_ms: float = 0.0,
        retry_count: int = 0,
    ):
        self.status = status
        self.payload = payload
        self.latency_ms = latency_ms
        self.retry_count = retry_count

    def __repr__(self):
        return (
            f"ToolResult(status={self.status!r}, "
            f"latency_ms={self.latency_ms}, retry_count={self.retry_count})"
        )