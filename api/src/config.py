from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://braydon@localhost:5432/assistant"
    database_url_sync: str = "postgresql://braydon@localhost:5432/assistant"
    anthropic_api_key: str = ""
    coach_model: str = "claude-sonnet-4-6"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
