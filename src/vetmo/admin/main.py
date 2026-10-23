"""Точка входа VETMO Admin: QApplication, контекст, главное окно (T-103).

Запуск из репозитория::

    .\\.venv\\Scripts\\python.exe -m vetmo.admin.main

Секреты читаются из ``%APPDATA%/VETMO/secrets.env`` (или
``VETMO_SYNC_SECRETS_FILE``); при ошибке показывается путь к файлу,
код возврата — 2.

Режим ``--self-check`` (используется смоуком сборочного скрипта): без окон и
диалогов проверяет, что приложение стартует и корректно сообщает об
отсутствии секретов. Код возврата: 0 — секреты загружены, 2 — секретов нет.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox

from vetmo import __version__
from vetmo.admin.context import create_admin_context
from vetmo.admin.window import AdminWindow
from vetmo.infra.config import Settings
from vetmo.infra.logging import get_logger, setup_logging
from vetmo.ui.theme import theme_for

_SELF_CHECK_FLAG = "--self-check"


def _self_check() -> int:
    """Проверка старта без GUI: настройка логов + чтение секретов.

    Возвращает 0, если секреты прочитаны, и 2, если их нет. Диалоги не
    показываются: в неинтерактивной сессии они заблокировали бы процесс.
    """
    setup_logging(Settings())
    logger = get_logger(__name__)
    try:
        context = create_admin_context()
    except RuntimeError as exc:
        logger.error("Self-check: секреты недоступны: %s", exc)
        return 2
    try:
        logger.info(
            "Self-check: секреты загружены из %s", context.secrets_path)
    finally:
        context.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Запускает Admin-приложение и возвращает код выхода."""
    args = list(sys.argv if argv is None else argv)
    if _SELF_CHECK_FLAG in args[1:]:
        return _self_check()

    QApplication.setApplicationName("VETMO Admin")
    QApplication.setApplicationVersion(__version__)
    app = QApplication(args)
    app.setStyleSheet(theme_for("dark"))
    setup_logging(Settings())
    logger = get_logger(__name__)

    try:
        context = create_admin_context()
    except RuntimeError as exc:
        logger.error("Не удалось загрузить секреты: %s", exc)
        QMessageBox.critical(
            None,
            "VETMO Admin — не удалось загрузить секреты",
            str(exc),
        )
        return 2

    window = AdminWindow(context)
    window.show()

    # Мягкое завершение: даём фоновым чтениям завершиться до закрытия клиентов.
    def _graceful_quit() -> None:
        QThreadPool.globalInstance().waitForDone(8000)

    app.aboutToQuit.connect(_graceful_quit)
    try:
        return app.exec()
    finally:
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
