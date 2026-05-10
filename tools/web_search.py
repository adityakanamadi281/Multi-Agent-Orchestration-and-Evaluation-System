import asyncio
import time
from exa_py import Exa
from schemas.tool_result import ToolResult
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_exa_semaphore = asyncio.Semaphore(settings.EXA_MAX_CONCURRENT)


class WebSearchTool:
    def __init__(self):
        self._exa = Exa(api_key=settings.EXA_API_KEY)

    async def search(self, query: str, num_results: int | None = None) -> ToolResult:
        num_results = num_results or settings.EXA_MAX_RESULTS

        if settings.EXA_MOCK:
            return self._mock_result(query)

        result = await self._exa_search(query, num_results)

        for attempt in range(1, settings.WEB_SEARCH_MAX_RETRIES + 1):
            if result.status == "ok":
                break
            if result.status == "timeout":
                short_query = " ".join(query.split()[:5])
                logger.warning("exa_timeout_retry", attempt=attempt, query=short_query)
                result = await self._exa_search(short_query, num_results)
                result.retry_count = attempt
            elif result.status in ("empty", "rate_limit"):
                logger.warning("exa_search_failed", reason=result.status, attempt=attempt)
                return result
            else:
                break

        return result

    async def find_similar(self, source_url: str, num_results: int = 3) -> ToolResult:
        async with _exa_semaphore:
            start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._exa.find_similar_and_contents,
                        source_url,
                        num_results=num_results,
                        text={"max_characters": settings.EXA_MAX_CHARACTERS},
                        exclude_source_domain=True,
                    ),
                    timeout=settings.EXA_TIMEOUT_SEC,
                )
                results = [
                    {
                        "url": r.url,
                        "title": r.title,
                        "content": r.text,
                        "relevance_score": self._normalize_score(r.score),
                        "hop": 2,
                    }
                    for r in response.results
                ]
                return ToolResult(
                    status="ok" if results else "empty",
                    payload={"source_url": source_url, "results": results},
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
            except asyncio.TimeoutError:
                return ToolResult(
                    status="timeout",
                    payload=None,
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
            except Exception as e:
                return self._handle_exa_error(e, start)

    async def _exa_search(self, query: str, num_results: int) -> ToolResult:
        async with _exa_semaphore:
            start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._exa.search_and_contents,
                        query,
                        type="auto",
                        num_results=num_results,
                        text={"max_characters": settings.EXA_MAX_CHARACTERS},
                        highlights={"num_sentences": 3, "highlights_per_url": 2},
                        summary={"query": query},
                    ),
                    timeout=settings.EXA_TIMEOUT_SEC,
                )
                results = [
                    {
                        "url": r.url,
                        "title": r.title,
                        "content": r.text,
                        "highlights": getattr(r, "highlights", None),
                        "summary": getattr(r, "summary", None),
                        "relevance_score": self._normalize_score(getattr(r, "score", None)),
                        "published_date": getattr(r, "published_date", None),
                    }
                    for r in response.results
                ]
                return ToolResult(
                    status="ok" if results else "empty",
                    payload={"results": results},
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
            except asyncio.TimeoutError:
                return ToolResult(
                    status="timeout",
                    payload=None,
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=0,
                )
            except Exception as e:
                return self._handle_exa_error(e, start)

    def _normalize_score(self, raw: float | None) -> float:
        if raw is None:
            return 0.0
        return min(max((raw - 0.10) / 0.25, 0.0), 1.0)

    def _handle_exa_error(self, error: Exception, start: float) -> ToolResult:
        latency = (time.monotonic() - start) * 1000
        msg = str(error).lower()
        if "429" in msg or "rate limit" in msg:
            return ToolResult(status="rate_limit", payload=None, latency_ms=latency, retry_count=0)
        if "401" in msg or "invalid api" in msg:
            raise EnvironmentError("EXA_API_KEY is invalid or missing")
        return ToolResult(status="malformed", payload=None, latency_ms=latency, retry_count=0)

    def _mock_result(self, query: str) -> ToolResult:
        return ToolResult(
            status="ok",
            payload={
                "results": [
                    {
                        "url": "https://mock.example.com/1",
                        "title": "Mock result 1",
                        "content": f"Mock content for query: {query}",
                        "relevance_score": 0.9,
                        "source": "mock",
                    },
                    {
                        "url": "https://mock.example.com/2",
                        "title": "Mock result 2",
                        "content": "Additional mock context for multi-hop reasoning.",
                        "relevance_score": 0.75,
                        "source": "mock",
                    },
                ]
            },
            latency_ms=10.0,
            retry_count=0,
        )