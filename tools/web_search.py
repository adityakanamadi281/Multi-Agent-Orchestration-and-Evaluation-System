import asyncio
from core.config import settings
from tools.base import BaseTool
from schemas.tool_result import ToolResult, ErrorCode


class WebSearchTool(BaseTool):
    name = "web_search"
    timeout_seconds = 15.0

    async def _execute(self, input: dict) -> ToolResult:
        query = input.get("query", "").strip()
        num_results = int(input.get("num_results", 5))

        if not query:
            return ToolResult(
                success=False,
                error_code=ErrorCode.MALFORMED,
                error_message="query must be non-empty string",
            )

        from exa_py import Exa

        client = Exa(api_key=settings.EXA_API_KEY)

        response = await asyncio.to_thread(
            client.search_and_contents,
            query,
            num_results=num_results,
            use_autoprompt=True,
            text={"max_characters": 1000},
        )

        results = [
            {
                "url": r.url,
                "title": r.title or "",
                "snippet": r.text or "",
                "relevance_score": float(r.score or 0.0),
            }
            for r in response.results
        ]

        if not results:
            return ToolResult(
                success=False,
                error_code=ErrorCode.EMPTY,
                data={"results": []},
                error_message="Exa returned zero results",
            )

        return ToolResult(success=True, data={"results": results})

