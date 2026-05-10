from enum import Enum
from typing import Any
from pydantic import BaseModel


class ErrorCode(str, Enum):
    TIMEOUT = "TIMEOUT"
    EMPTY = "EMPTY"
    MALFORMED = "MALFORMED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None
    latency_ms: int = 0


