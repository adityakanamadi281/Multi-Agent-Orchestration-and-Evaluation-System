from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    EXA_API_KEY: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://multiagent:multiagent@localhost:5432/multiagent"
    SYNC_DATABASE_URL: str = "postgresql://multiagent:multiagent@localhost:5432/multiagent"
    REDIS_URL: str = "redis://localhost:6379"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_API_KEY: str = "ollama"
    CHROMA_PERSIST_DIR: str = "/data/chroma"
    LOG_LEVEL: str = "INFO"
    MODEL_NAME: str = "gemma4:31b-cloud"
    





settings = Settings()



