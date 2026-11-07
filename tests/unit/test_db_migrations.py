"""Регрессия: пустая SQLite должна догонять схему до head."""

from pathlib import Path

from sqlalchemy import inspect

from vetmo.data.db import create_db, migrate


def test_migrate_creates_user_settings(tmp_path: Path) -> None:
    """sync не должен падать на ``no such table: user_settings``."""
    db_path = tmp_path / "empty.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine, _ = create_db(url)
    try:
        migrate(engine, url)
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert "user_settings" in tables
    assert "heroes" in tables
    assert "meta_snapshots" in tables
