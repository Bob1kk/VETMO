"""Тесты ``SyncRunner`` (T-102): сигналы, режимы и отмена.

Сеть не используется: ``sync_all`` всегда подменяется моком.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from vetmo.admin import workers
from vetmo.admin.workers import SyncRunner
from vetmo.services.stratz_sync import SyncStats


@pytest.fixture()
def context() -> MagicMock:
    """Контекст не нужен ``run()``: sync_all сам читает секреты."""
    return MagicMock()


def test_sync_runner_meta_calls_sync_all_with_expected_flags(
    monkeypatch: pytest.MonkeyPatch,
    context: MagicMock,
) -> None:
    calls: dict[str, object] = {}

    def fake_sync_all(**kwargs: object) -> SyncStats:
        calls.update(kwargs)
        return SyncStats()

    monkeypatch.setattr(workers, "sync_all", fake_sync_all)

    runner = SyncRunner("meta", context)
    runner.run()

    assert calls["dry_run"] is False
    assert calls["include_matchups"] is False
    assert calls["trigger"] == "admin-app"
    assert isinstance(calls["request_id"], str)
    assert calls["request_id"]
    assert callable(calls["progress"])
    assert callable(calls["should_stop"])


def test_sync_runner_emits_finished(
    monkeypatch: pytest.MonkeyPatch,
    context: MagicMock,
) -> None:
    stats = SyncStats(
        patch_id=123,
        patch_version="7.40",
        rows_meta=42,
        rows_matchups=7,
        slices=3,
        period="2026-10-10",
    )

    def fake_sync_all(**kwargs: object) -> SyncStats:
        progress = kwargs["progress"]
        assert isinstance(progress, Callable)
        progress("  rank=0 pos=0: 127 строк")
        return stats

    monkeypatch.setattr(workers, "sync_all", fake_sync_all)

    runner = SyncRunner("full", context)
    finished: list[dict[str, object]] = []
    messages: list[str] = []
    runner.finished.connect(finished.append)
    runner.progress.connect(messages.append)
    runner.run()

    assert messages == ["  rank=0 pos=0: 127 строк"]
    assert len(finished) == 1
    payload = finished[0]
    assert payload["patch_id"] == 123
    assert payload["patch_version"] == "7.40"
    assert payload["rows_meta"] == 42
    assert payload["rows_matchups"] == 7
    assert payload["slices"] == 3
    assert payload["period"] == "2026-10-10"
    assert payload["errors"] == []
    assert payload["status"] == "ok"
    assert payload["cancelled"] is False
    assert payload["mode"] == "full"


def test_sync_runner_emits_failed_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    context: MagicMock,
) -> None:
    def boom(**kwargs: object) -> SyncStats:
        raise RuntimeError("STRATZ недоступен")

    monkeypatch.setattr(workers, "sync_all", boom)

    runner = SyncRunner("dry", context)
    failures: list[str] = []
    finished: list[dict[str, object]] = []
    runner.failed.connect(failures.append)
    runner.finished.connect(finished.append)
    runner.run()

    assert failures == ["RuntimeError: STRATZ недоступен"]
    assert finished == []


def test_cancel_sets_flag(context: MagicMock) -> None:
    runner = SyncRunner("meta", context)

    assert runner._should_stop() is False

    runner.cancel()

    assert runner._should_stop() is True
    assert runner._summary(SyncStats())["status"] == "partial"
    assert runner._summary(SyncStats())["cancelled"] is True
