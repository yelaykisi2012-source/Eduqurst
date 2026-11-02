"""Alembic environment — wired to EduQuest's app.config + models."""
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import Base
import app.models  # noqa: F401  (registers all tables on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL comes from backend/.env. Alembic prefers the DIRECT (unpooled) URL so
# DDL works reliably; falls back to DATABASE_URL. App runtime still uses pooled.
target_url = get_settings().migration_database_url
config.set_main_option("sqlalchemy.url", target_url)

target_metadata = Base.metadata


def announce_target() -> None:
    """Name the database before anything is changed, and say so LOUDLY.

    .env wins over a shell `DATABASE_URL=...` here (settings reads both, and the
    unpooled URL is the one Alembic prefers), so a "harmless local dry run" can
    quietly migrate production. Printing host + database makes that impossible to
    miss: the line sits right above the first "Running upgrade" in the log.
    """
    url = make_url(target_url)
    logging.getLogger("alembic.env").warning(
        "Alembic will change host=%s database=%s", url.host, url.database
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    announce_target()
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
