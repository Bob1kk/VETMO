"""GUI-смоук: окно, оверлей, рекомендации, первый автосинк каталога.

Запуск: .\\.venv\\Scripts\\python.exe -m vetmo.ui._smoke
Ожидаемо: exit 0, печатается GUI_SMOKE_OK. Сеть не блокирует UI (worker);
смок ждёт завершения статусных задач, максимум ~40 с.
"""

import sys

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from vetmo.main import build_app


def main() -> int:
    """Смоук: окно -> оверлей показать/hide -> рекомендации -> выход."""
    app = QApplication(sys.argv)
    window = build_app()
    window.show()

    def show_overlay() -> None:
        window._apply_overlay_visibility(True)  # noqa: SLF001 — смоук в пакете

    def check_overlay() -> None:
        assert window._overlay.isVisible(), "Оверлей должен быть виден"
        assert window._toggle_overlay.text() == "Скрыть оверлей", (
            "Кнопка должна читать «Скрыть оверлей»")
        window._refresh_overlay()
        QTimer.singleShot(1200, hide_overlay)

    def hide_overlay() -> None:
        window._apply_overlay_visibility(False)
        assert not window._overlay.isVisible()
        assert window._toggle_overlay.text() == "Запустить оверлей"
        QTimer.singleShot(4000, await_idle)

    def await_idle() -> None:
        """Дожидается окончания статусных задач (первый автосинк и т.п.)."""
        status = window.status_label_text()
        if status.startswith("⏳") or "Синхрониз" in status:
            QTimer.singleShot(2000, await_idle)
            return
        quit_when_idle()

    def quit_when_idle() -> None:
        QTimer.singleShot(300, app.quit)

    QTimer.singleShot(600, show_overlay)
    QTimer.singleShot(1100, check_overlay)

    # Мягкое завершение: дождаться воркеров (сеть/БД), но не вечно.
    def _graceful_quit_on_about() -> None:
        QThreadPool.globalInstance().waitForDone(30000)

    app.aboutToQuit.connect(_graceful_quit_on_about)
    exit_code = app.exec()
    window.hide()
    heroes = window._ctx.hero_count()  # noqa: SLF001 — смоук в пакете
    print(f"GUI_SMOKE_OK heroes={heroes}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
