"""Настройка логирования: файл + консоль, ротация. Публичный контракт T-003."""

import logging
import logging.handlers
from pathlib import Path

from vetmo.infra.config import Settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(settings: Settings) -> None:
    """Инициализирует root-логгер: RotatingFileHandler + StreamHandler (идемпотентно)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()  # идемпотентность: перезаписываем конфигурацию
    formatter = logging.Formatter(_FORMAT)

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    """Возвращает именованный логгер приложения."""
    return logging.getLogger(name)
