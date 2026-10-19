"""Alembic env для VETMO: URL из окружения или из файла конфигурации."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from vetmo.data.models_orm import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_db_url_env = os.environ.get("VETMO_DATABASE_URL")
_db_url_cfg = config.get_main_option("sqlalchemy.url")
_DB_URL = _db_url_env or _db_url_cfg or "sqlite:///vetmo.db"


def run_migrations_offline() -> None:
    """Офлайн-режим: только emit DDL, без DBAPI."""
    context.configure(
        url=_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Онлайн-режим: реальный engine; URL override через окружение."""
    section = config.get_section(config.config_ini_section, {})
    if section is not None:
        section["sqlalchemy.url"] = _DB_URL
    connectable = engine_from_config(
        section or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
