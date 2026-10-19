"""Тесты логирования (T-003)."""

import logging
import logging.handlers
from pathlib import Path

from vetmo.infra.config import Settings
from vetmo.infra.logging import setup_logging


def _make_settings(log_file: Path) -> Settings:
    return Settings(_env_file=None, log_file=str(log_file))


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    """setup_logging создаёт папку и пишет запись в файл."""
    log_file = tmp_path / "logs" / "vetmo.log"
    setup_logging(_make_settings(log_file))
    logging.getLogger("vetmo.test").info("привет")
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            h.flush()
    assert log_file.exists()
    assert "привет" in log_file.read_text(encoding="utf-8")


def test_setup_logging_respects_level(tmp_path: Path) -> None:
    """Уровень берётся из settings.log_level."""
    settings = Settings(_env_file=None, log_level="WARNING", log_file=str(tmp_path / "a.log"))
    setup_logging(settings)
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_idempotent_no_duplicate_handlers(tmp_path: Path) -> None:
    """Повторный вызов не плодит дубли обработчиков на root."""
    settings = Settings(_env_file=None, log_file=str(tmp_path / "b.log"))
    setup_logging(settings)
    before = len(logging.getLogger().handlers)
    setup_logging(settings)
    assert len(logging.getLogger().handlers) == before
