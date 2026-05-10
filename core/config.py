from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_API_KEY: str = "ollama"
    MODEL_NAME: str = "gemma4:31b-cloud"

    EXA_API_KEY: str = ""
    EXA_MOCK: bool = False
    EXA_MAX_RESULTS: int = 5
    EXA_MAX_CHARACTERS: int = 2000
    EXA_TIMEOUT_SEC: int = 8
    EXA_MAX_CONCURRENT: int = 5

    WEB_SEARCH_PRIMARY: str = "exa"
    WEB_SEARCH_MAX_RETRIES: int = 2

    DATABASE_URL: str = "postgresql+asyncpg://multiagent:multiagent@localhost:5432/multiagent"
    SYNC_DATABASE_URL: str = "postgresql://multiagent:multiagent@localhost:5432/multiagent"
    POSTGRES_USER: str = "multiagent"
    POSTGRES_PASSWORD: str = "multiagent"
    POSTGRES_DB: str = "multiagent"

    REDIS_URL: str = "redis://127.0.0.1:6379"

    CHROMA_PERSIST_DIR: str = "/data/chroma"

    CODE_SANDBOX_TIMEOUT_SEC: int = 10

    LOG_LEVEL: str = "INFO"


settings = Settings()