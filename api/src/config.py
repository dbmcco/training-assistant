from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres@127.0.0.1:5432/assistant"
    database_url_sync: str = "postgresql://postgres@127.0.0.1:5432/assistant"
    db_connect_timeout_seconds: float = 6.0
    db_command_timeout_seconds: float = 20.0
    db_statement_timeout_ms: int = 15000
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: float = 10.0
    db_pool_recycle_seconds: int = 1800
    anthropic_api_key: str = ""
    coach_model: str = "claude-sonnet-4-6"
    coach_prompt_history_messages: int = 8
    coach_memory_enabled: bool = True
    coach_memory_retrieval_limit: int = 6
    coach_memory_backfill_limit_messages: int = 2000
    coach_memory_embedding_dim: int = 256
    cors_origins: list[str] = ["http://localhost:5173"]
    garmin_writeback_enabled: bool = True
    garmin_writeback_repo: str = ""
    garmin_writeback_python: str = ""
    garmin_refresh_enabled: bool = True
    garmin_refresh_repo: str = ""
    garmin_refresh_python: str = ""
    garmin_refresh_timeout_seconds: int = 90
    garmin_refresh_min_interval_seconds: int = 120
    garmin_refresh_days_back: int = 1
    plan_ownership_mode: str = "assistant"
    assistant_plan_default_days_ahead: int = 14
    assistant_plan_lock_window_days: int = 2
    assistant_plan_sync_days: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
