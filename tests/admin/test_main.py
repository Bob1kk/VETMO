"""Тесты точки входа VETMO Admin: режим --self-check (T-114)."""

from __future__ import annotations

import logging

import pytest

from vetmo.admin import main as admin_main


@pytest.fixture()
def restore_root_logging():
    """Возвращает root-логгер в исходное состояние (setup_logging его чистит)."""
    root = logging.getLogger()
    saved = root.handlers[:]
    level = root.level
    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in saved:
                handler.close()
        root.handlers[:] = saved
        root.setLevel(level)


def test_self_check_without_secrets_returns_2_and_writes_log(
    tmp_path, monkeypatch, restore_root_logging
) -> None:
    """`--self-check` без секретов: код 2, лог создан, диалогов нет."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv(
        "VETMO_SYNC_SECRETS_FILE", str(tmp_path / "no-such-secrets.env"))
    log_path = tmp_path / "logs" / "vetmo.log"
    monkeypatch.setenv("VETMO_LOG_FILE", str(log_path))

    assert admin_main._self_check() == 2

    assert log_path.exists()
    assert "Self-check" in log_path.read_text(encoding="utf-8")


def test_main_dispatches_self_check_without_gui(
    tmp_path, monkeypatch, restore_root_logging
) -> None:
    """main(argv) с --self-check не создаёт QApplication и возвращает код."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv(
        "VETMO_SYNC_SECRETS_FILE", str(tmp_path / "no-such-secrets.env"))
    monkeypatch.setenv("VETMO_LOG_FILE", str(tmp_path / "logs" / "vetmo.log"))

    assert admin_main.main(["VETMO-Admin.exe", "--self-check"]) == 2
