from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}

if settings.database_url.startswith("postgresql+asyncpg://"):
    engine_kwargs.update(
        {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout_seconds,
            "pool_recycle": settings.db_pool_recycle_seconds,
            "connect_args": {
                "timeout": settings.db_connect_timeout_seconds,
                "command_timeout": settings.db_command_timeout_seconds,
                "server_settings": {
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                },
            },
        }
    )

engine = create_async_engine(settings.database_url, **engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def check_db_ready() -> bool:
    """Return True when the DB accepts a simple query."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
