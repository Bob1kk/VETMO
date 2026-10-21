"""Точка входа VETMO Admin: QApplication, контекст, главное окно (T-103).

Запуск из репозитория::

    .\\.venv\\Scripts\\python.exe -m vetmo.admin.main

Секреты читаются из ``%APPDATA%/VETMO/secrets.env`` (или
``VETMO_SYNC_SECRETS_FILE``); при ошибке показывается путь к файлу,
код возврата — 2.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox

from vetmo import __version__
from vetmo.admin.context import create_admin_context
from vetmo.admin.window import AdminWindow
from vetmo.ui.theme import theme_for


def main(argv: list[str] | None = None) -> int:
    """Запускает Admin-приложение и возвращает код выхода."""
    QApplication.setApplicationName("VETMO Admin")
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv if argv is None else argv)
    app.setStyleSheet(theme_for("dark"))

    try:
        context = create_admin_context()
    except RuntimeError as exc:
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
