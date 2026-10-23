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
from PySide6.QtCore import QCoreApplication, QThreadPool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.db import create_db, migrate
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.services.live_news import LiveNewsService

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
    """Автономное окружение: все сетевые точки заглушены до build_app."""
    monkeypatch.setenv(
        "VETMO_DB_URL", f"sqlite:///{(tmp_path / 'ui.db').as_posix()}")
    # SupabaseGateway.select — заглушка для чтения reference-данных
    monkeypatch.setattr(
        SupabaseGateway,
        "select",
        lambda self, table, *args, **kwargs: [],
    )
    monkeypatch.setattr(
        SupabaseGateway,
        "rpc",
        lambda self, name, params: [],
    )
    monkeypatch.setattr(
        SupabaseGateway,
        "is_configured",
        property(lambda self: False),
    )
    # LiveNewsService.get_latest_patch_news — заглушка новостей
    monkeypatch.setattr(
        LiveNewsService,
        "get_latest_patch_news",
        lambda self, limit=5: ([], True),
    )


def _drain_workers() -> None:
    """Хвост синхронизации: ждём QThreadPool, чтобы не утечь в другой тест."""
    pool = QThreadPool.globalInstance()
    app = QCoreApplication.instance()
    for _ in range(5):
        if app is not None:
            app.processEvents()
        pool.waitForDone(8000)
        if app is not None:
            app.processEvents()
        if pool.activeThreadCount() == 0:
            return


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
