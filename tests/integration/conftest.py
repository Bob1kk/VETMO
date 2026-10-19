"""Фикстуры интеграционных тестов UI (T-017/T-018).

Ключевое правило QA: сеть полностью заглушена ДО build_app
(OpenDota, Supabase, NewsService), иначе авто-синк на пустой БД полез
в сеть. SQLite-файл БД задаётся через VETMO_DB_URL до создания
application context (он строится внутри build_app -> create_app_context).
"""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QThreadPool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.db import create_db, migrate
from vetmo.infra.supabase_stub import SupabaseClient
from vetmo.services.news_service import NewsService
from vetmo.services.opendota_client import OpenDotaClient, SyncResult

if TYPE_CHECKING:
    from vetmo.ui.main_window import MainWindow


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    """Файловая SQLite с применённой миграцией (как в unit-конфте)."""
    url = f"sqlite:///{(tmp_path / 'int.db').as_posix()}"
    engine, sessionmaker = create_db(url)
    migrate(engine, url)
    yield engine, sessionmaker
    engine.dispose()


@pytest.fixture()
def app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Автономное окружение: tmp SQLite + все сетевые точки заглушены."""
    monkeypatch.setenv(
        "VETMO_DB_URL", f"sqlite:///{(tmp_path / 'ui.db').as_posix()}")
    monkeypatch.setattr(
        OpenDotaClient,
        "sync_heroes",
        lambda self, limit=120: SyncResult(total=0, ok=0),
    )
    monkeypatch.setattr(
        OpenDotaClient,
        "sync_matchups",
        lambda self, hero_ids=None, rivals_per_hero=30: SyncResult(
            total=0, ok=0),
    )
    monkeypatch.setattr(
        SupabaseClient,
        "sync_meta_snapshot",
        lambda self, limit=50: {"enabled": False, "sent": 0},
    )
    monkeypatch.setattr(
        NewsService,
        "get_latest_patch_news",
        lambda self, limit=5: ([], True),
    )


def _drain_workers() -> None:
    """Хвост синхронизации: ждём QThreadPool, чтобы не утечь в другой тест."""
    QThreadPool.globalInstance().waitForDone(8000)


@pytest.fixture()
def make_window(app_env, qtbot) -> Iterator[Callable[[], "MainWindow"]]:
    """Фабрика MainWindow: замеряет время сборки+show (<3 c, NFR-001)."""
    from vetmo.main import build_app  # noqa: PLC0415 — импорт до замера

    created: dict[str, MainWindow] = {}

    def _make() -> "MainWindow":
        assert not created, "окно уже создано этим инстансом фикстуры"
        start = time.perf_counter()
        window = build_app()
        window.show()
        elapsed = time.perf_counter() - start
        # whitebox-хук: test_main_window проверяет elapsed < 3.0
        window._build_seconds = elapsed
        qtbot.addWidget(window)
        created["window"] = window
        return window

    yield _make

    window = created.get("window")
    if window is not None:
        window.close()
    _drain_workers()
