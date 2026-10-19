"""Общая фикстура БД для unit-тестов сервисов (qa-agent позже расширит)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.db import create_db, migrate


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[tuple[object, sessionmaker[Session]]]:
    """Файловая SQLite с применённой миграцией: (engine, sessionmaker)."""
    url = f"sqlite:///{(tmp_path / 'svc.db').as_posix()}"
    engine, sessionmaker = create_db(url)
    migrate(engine, url)
    yield engine, sessionmaker
    engine.dispose()
