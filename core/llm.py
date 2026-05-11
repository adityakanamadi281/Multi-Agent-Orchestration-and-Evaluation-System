from openai import AsyncOpenAI
from core.config import settings


_llm_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            base_url=settings.OLLAMA_BASE_URL,
            api_key=settings.OLLAMA_API_KEY,
            timeout=settings.LLM_TIMEOUT_SEC,
        )
    return _llm_client


async def llm_call(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
    stream: bool = False,
):
    client = get_llm_client()
    kwargs: dict = dict(
        model=settings.MODEL_NAME,
        messages=messages,
        temperature=0.1,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if stream:
        kwargs["stream"] = True
    return await client.chat.completions.create(**kwargs)