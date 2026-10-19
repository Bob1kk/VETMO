"""Точка входа VETMO (T-020): QApplication, сервисы, тема, главное окно.

build_app() возвращает настроенное MainWindow — им пользуются
packaging-agent (PyInstaller) и QA-смоук.
"""

import sys


def build_app():
    """Собирает приложение: БД, сервисы, тема QSS, MainWindow.

    Без вызова app.exec() — QApplication обязана существовать заранее
    (main() создаёт её; смоук тоже может).
    """
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415 — поздний импорт старта <3 c

    from vetmo.ui.app_context import create_app_context  # noqa: PLC0415
    from vetmo.ui.main_window import MainWindow  # noqa: PLC0415
    from vetmo.ui.theme import theme_for  # noqa: PLC0415

    context = create_app_context()
    theme = context.settings_service.get_theme()
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(theme_for(theme))
    return MainWindow(context)


def main() -> int:
    """Запуск приложения через py -m vetmo.main или exe."""
    from PySide6.QtCore import QThreadPool  # noqa: PLC0415
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from vetmo import __version__  # noqa: PLC0415

    QApplication.setApplicationName("VETMO")
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)

    window = build_app()
    window.show()

    # Мягкое завершение: дождаться воркеров (сеть/БД), но не вечно.
    def _graceful_quit() -> None:
        window.hide()
        QThreadPool.globalInstance().waitForDone(8000)

    app.aboutToQuit.connect(_graceful_quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
