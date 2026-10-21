"""Иконка приложения VETMO: файлы рядом с проектом или внутри one-file бандла."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap

_ICON_NAMES = ("vetmo_icon.ico", "vetmo_icon.bmp")


def _base_dir() -> Path:
    """Каталог, где лежат vetmo_icon.* (корень проекта или _MEIPASS)."""
    meip = getattr(sys, "_MEIPASS", None)
    if meip:
        return Path(meip)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def app_icon_path() -> Path | None:
    """Первый найденный файл иконки или None."""
    for name in _ICON_NAMES:
        candidate = _base_dir() / name
        if candidate.is_file():
            return candidate
    return None


def app_icon() -> QIcon:
    """Иконка окна/таскбара; null-QIcon, если файла нет."""
    path = app_icon_path()
    return QIcon(str(path)) if path is not None else QIcon()


def rounded_brand_pixmap(size: int = 40, radius: int = 10) -> QPixmap:
    """Квадратная обрезанная иконка со скруглёнными углами для шапки."""
    path = app_icon_path()
    if path is None:
        return QPixmap()
    source = QPixmap(str(path))
    if source.isNull():
        return QPixmap()

    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size) // 2)
    y = max(0, (scaled.height() - size) // 2)
    cropped = scaled.copy(QRect(x, y, size, size))

    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result
