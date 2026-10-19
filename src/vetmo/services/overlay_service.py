"""Сервис оверлея: мост к окну через провайдер, без импортов Qt. Контракт T-012."""

from collections.abc import Callable
from typing import Any

from vetmo.services.settings_service import SettingsService


class OverlayService:
    """Управляет видимостью/обновлением окна оверлея (окно привязывается GUI)."""

    def __init__(self, settings_service: SettingsService) -> None:
        self._settings = settings_service
        self._get_window: Callable[[], Any] | None = None

    def bind_window(self, get_window: Callable[[], Any]) -> None:
        """Регистрирует провайдер окна (GUI привяжет позже; окно может отсутствовать)."""
        self._get_window = get_window

    def _call(self, method_name: str) -> None:
        """Вызывает метод окна, если окно есть; иначе no-op."""
        if self._get_window is None:
            return
        window = self._get_window()
        if window is None:
            return
        method = getattr(window, method_name, None)
        if callable(method):
            method()

    def show(self) -> None:
        """Показывает оверлей (make visible)."""
        self._call("show_overlay")

    def hide(self) -> None:
        """Скрывает оверлей (make hidden)."""
        self._call("hide_overlay")

    def update(self) -> None:
        """Пинг обновления рекомендаций/шага."""
        self._call("update_overlay")
