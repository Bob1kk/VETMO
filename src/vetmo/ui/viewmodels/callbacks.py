"""Простые callback-«сигналы» для viewmodels без импортов Qt (NFR-005)."""

from collections.abc import Callable
from typing import Any


class CallbackList:
    """Список подписчиков-колбэков: Lisp-подобные «сигналы» без Qt."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[..., Any]] = []

    def subscribe(self, callback: Callable[..., Any]) -> None:
        """Добавляет подписчика (без дублей)."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[..., Any]) -> None:
        """Удаляет подписчика, если он был подписан."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Вызывает всех подписчиков; ошибка одного не роняет остальных."""
        for callback in list(self._callbacks):
            try:
                callback(*args, **kwargs)
            except Exception:  # noqa: BLE001 — наблюдатель не может ронять VM
                continue
