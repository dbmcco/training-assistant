from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from src.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Tables that already exist in the database and must NOT be managed by Alembic
EXCLUDED_TABLES = {"garmin_activities", "garmin_daily_summary", "athlete_biometrics"}

# Only manage tables defined in our SQLAlchemy models (minus excluded ones)
MANAGED_TABLES = {
    table.name for table in Base.metadata.sorted_tables
} - EXCLUDED_TABLES


def include_name(name, type_, parent_names):
    """Filter database objects during reflection. Only reflect tables that
    are defined in our models and not excluded, so Alembic does not try
    to drop unrelated tables that happen to live in the same database."""
    if type_ == "table":
        return name in MANAGED_TABLES
    return True


def include_object(object, name, type_, reflected, compare_to):
    """Filter objects during autogenerate comparison. Skip any reflected
    database object whose table is not in our managed set."""
    if type_ == "table":
        return name in MANAGED_TABLES
    # For columns, indexes, constraints etc., check the parent table
    if hasattr(object, "table") and object.table is not None:
        return object.table.name in MANAGED_TABLES
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
