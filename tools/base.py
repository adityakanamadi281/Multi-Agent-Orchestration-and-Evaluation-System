from abc import ABC, abstractmethod
from schemas.tool_result import ToolResult


class BaseTool(ABC):
    name: str = "base_tool"

    @abstractmethod
    async def execute(self, input: dict) -> ToolResult:
        raise NotImplementedError