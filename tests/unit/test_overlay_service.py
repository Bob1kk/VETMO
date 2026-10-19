"""Тесты OverlayService (T-012, сервисная часть): bind/show/hide/update, без Qt."""

from typing import Any

from vetmo.services.overlay_service import OverlayService
from vetmo.services.settings_service import SettingsService


class FakeWindow:
    """Дублёр окна: считает вызовы (настоящее окно создаст GUI-агент)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def show_overlay(self) -> None:
        self.calls.append("show")

    def hide_overlay(self) -> None:
        self.calls.append("hide")

    def update_overlay(self) -> None:
        self.calls.append("update")


def _svc(db) -> OverlayService:
    _, sessionmaker = db
    return OverlayService(SettingsService(sessionmaker))


def test_actions_no_window_noop(db) -> None:
    """Без окна — no-op, без исключений."""
    svc = _svc(db)
    svc.show()
    svc.hide()
    svc.update()


def test_bind_and_calls(db) -> None:
    """После bind_window методы окна пингуются."""
    svc = _svc(db)
    win = FakeWindow()
    svc.bind_window(lambda: win)
    svc.show()
    svc.hide()
    svc.update()
    assert win.calls == ["show", "hide", "update"]


def test_window_none_is_noop(db) -> None:
    """Провайдер вернул None (окно ещё не создано) — no-op."""
    svc = _svc(db)
    svc.bind_window(lambda: None)
    svc.show()
    svc.hide()
    svc.update()


def test_window_missing_method_is_noop(db) -> None:
    """Окно без метода show_overlay — getattr no-op."""
    svc = _svc(db)
    dummy: Any = object()
    svc.bind_window(lambda: dummy)
    svc.show()
    svc.hide()
    svc.update()
