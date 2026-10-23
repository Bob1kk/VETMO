"""Выбор монитора для лаунчера и оверлея.

По умолчанию (-1) используется второй монитор, если он есть: Dota 2 обычно
запущена на основном, а помощник не должен перекрывать игру. Пользователь
может явно выбрать монитор в настройках.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

_FALLBACK_MARGIN = 24


def available_screens() -> list[QScreen]:
    """Список экранов в порядке Qt (0 — основной)."""
    return list(QGuiApplication.screens())


def resolve_screen(index: int) -> QScreen | None:
    """Экран по индексу; -1 — второй, если есть, иначе основной."""
    screens = available_screens()
    if not screens:
        return None
    if 0 <= index < len(screens):
        return screens[index]
    if index < 0 and len(screens) > 1:
        return screens[1]
    return screens[0]


def screen_label(index: int, screen: QScreen) -> str:
    """Человекочитаемое имя монитора для combo."""
    geometry = screen.geometry()
    name = screen.name() or f"Монитор {index + 1}"
    return f"{name} · {geometry.width()}×{geometry.height()}"


def move_launcher_to_screen(window: QWidget, screen: QScreen | None) -> None:
    """Ставит лаунчер по центру выбранного экрана (не поверх Dota)."""
    if screen is None:
        return
    area: QRect = screen.availableGeometry()
    width = min(window.width(), max(640, area.width() - 2 * _FALLBACK_MARGIN))
    height = min(window.height(), max(480, area.height() - 2 * _FALLBACK_MARGIN))
    x = area.x() + max(0, (area.width() - width) // 2)
    y = area.y() + max(0, (area.height() - height) // 2)
    window.setGeometry(x, y, width, height)


def overlay_top_left(screen: QScreen | None, x: int, y: int) -> QPoint:
    """Абсолютная позиция оверлея: смещение относительно выбранного экрана."""
    if screen is None:
        return QPoint(int(x), int(y))
    area = screen.availableGeometry()
    px = area.x() + max(0, min(int(x), max(0, area.width() - 80)))
    py = area.y() + max(0, min(int(y), max(0, area.height() - 80)))
    return QPoint(px, py)


__all__ = [
    "available_screens",
    "move_launcher_to_screen",
    "overlay_top_left",
    "resolve_screen",
    "screen_label",
]
