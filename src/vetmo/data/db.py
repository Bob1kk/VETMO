"""Утилиты БД: engine, sessionmaker, WAL, программная миграция. Контракт T-004."""

from collections.abc import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_MIGRATIONS_DIR = "src/vetmo/data/migrations"


def _configure_sqlite(dbapi_connection: object, _record: object) -> None:
    """PRAGMAs для нового sqlite-соединения: WAL + foreign_keys."""
    import sqlite3

    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db(db_url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Создаёт Engine и sessionmaker (expire_on_commit=False), без I/O на старте."""
    engine = _create_engine_with_hooks(db_url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _create_engine_with_hooks(db_url: str) -> Engine:
    """Engine + event-хуки; для не-sqlite URL хуки не ставятся."""
    from sqlalchemy import create_engine

    engine = create_engine(db_url)
    if db_url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def migrate(engine: Engine, db_url: str | None = None) -> None:
    """Программный прогон Alembic миграций до head."""
    config = Config()
    config.set_main_option("script_location", _MIGRATIONS_DIR)
    url = db_url or str(engine.url)
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


def session_factory(engine: Engine) -> Callable[[], Session]:
    """Фабрика сессий для инфраструктурного слоя."""
    return sessionmaker(bind=engine, expire_on_commit=False)
