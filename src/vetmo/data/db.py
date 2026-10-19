"""Утилиты БД: engine, sessionmaker, WAL, программная миграция. Контракт T-004."""

import sys
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _migrations_dir() -> str:
    """Папка миграций Alembic: рядом с пакетом — работает и в dev, и в PyInstaller.

    - Dev: `src/vetmo/data/migrations` ( path(__file__).parent / "migrations" ).
    - PyInstaller one-file: data-файлы распакованы в sys._MEIPASS с сохранением
      структуры пакета (vetmo/data/migrations), а `__file__` ссылаeтся туда же.
    Вариант с env `VETMO_MIGRATIONS_DIR` — принудительный override (тесты/нестандартные сборки).
    """
    import os

    override = os.environ.get("VETMO_MIGRATIONS_DIR")
    if override:
        return override
    here = Path(__file__).resolve().parent / "migrations"
    if not here.exists() and getattr(sys, "frozen", False):
        meip = getattr(sys, "_MEIPASS", None)
        if meip:
            candidate = Path(meip) / "vetmo" / "data" / "migrations"
            if candidate.exists():
                return str(candidate)
    return str(here)


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
    config.set_main_option("script_location", _migrations_dir())
    url = db_url or str(engine.url)
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


def session_factory(engine: Engine) -> Callable[[], Session]:
    """Фабрика сессий для инфраструктурного слоя."""
    return sessionmaker(bind=engine, expire_on_commit=False)
