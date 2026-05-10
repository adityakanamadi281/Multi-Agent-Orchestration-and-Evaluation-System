from openai import AsyncOpenAI
from core.config import settings


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OLLAMA_BASE_URL,
        api_key=settings.OLLAMA_API_KEY,
    )





