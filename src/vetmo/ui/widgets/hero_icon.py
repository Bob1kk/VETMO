"""Иконки героев: локальный кэш первые, CDN-URL, круглый плейсхолдер (R2).

Порядок разрешения иконки (задача A/B R2):
1) локальный файл ``assets/cache/icons/{hero_id}.png``;
2) сеть через IconFetcher по icon_url / CDN-ссылке из internal_name;
3) цветной круг с инициалами (placeholder_pixmap).
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

_ICON_SIZE = 34

_PALETTE = (
    "#5B8DEF", "#3FB68B", "#E0A458", "#9C6FE0", "#53C7DC",
    "#E05661", "#7CB342", "#F06292", "#8D6E63", "#26A69A",
)

_CDN_BASE = "https://cdn.dota2.com/apps/dota2/images/dota_react/heroes/icons/"

_PACKAGE_ROOT = Path(__file__).resolve().parents[4]


def _icon_dir() -> Path:
    """Каталог локального кэша иконок (первый существующий вариант).

    В one-file exe иконки лежат в ``sys._MEIPASS/assets/cache/icons``.
    """
    candidates: list[Path] = []
    meip = getattr(sys, "_MEIPASS", None)
    if meip:
        candidates.append(Path(meip) / "assets" / "cache" / "icons")
    candidates.extend((
        _PACKAGE_ROOT / "assets" / "cache" / "icons",
        Path.cwd() / "assets" / "cache" / "icons",
    ))
    for directory in candidates:
        if directory.is_dir():
            return directory
    return candidates[0]


def local_hero_icon(hero_id: int | None) -> QPixmap | None:
    """Иконка из локального кэша или None (сеть не трогаем)."""
    if hero_id is None:
        return None
    path = _icon_dir() / f"{int(hero_id)}.png"
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    return None if pixmap.isNull() else pixmap


def cdn_icon_url(internal_name: str | None) -> str:
    """CDN-URL иконки по internal_name («npc_dota_hero_abaddon» и т.п.)."""
    name = str(internal_name or "").strip()
    if not name:
        return ""
    if not name.startswith("npc_dota_hero_"):
        name = f"npc_dota_hero_{name}"
    return f"{_CDN_BASE}{name}.png"


def placeholder_pixmap(name: str, size: int = _ICON_SIZE) -> QPixmap:
    """Цветной круг с инициалами вместо иконки (офлайн/нет файла>)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    initials = "".join(word[0] for word in name.split()[:2]).upper() or "?"
    color = QColor(_PALETTE[sum(map(ord, name)) % len(_PALETTE)])
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(color)
    painter.drawEllipse(0, 0, size - 1, size - 1)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont()
    font.setPixelSize(int(size * 0.42))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initials)
    painter.end()
    return pixmap


def scale_icon(
    pixmap: QPixmap, size: int = _ICON_SIZE, radius: int | None = None,
) -> QPixmap:
    """Центральный квадратный кроп + smooth-масштаб + скругление.

    Иконки Dota 2 — широкие (16:9). KeepAspectRatio в квадратном QLabel
    оставлял прозрачные поля сверху/снизу; здесь кадрируем по центру и
    рисуем в скруглённый квадрат.
    """
    if pixmap.isNull():
        return QPixmap()
    width, height = pixmap.width(), pixmap.height()
    side = min(width, height)
    left = max(0, (width - side) // 2)
    top = max(0, (height - side) // 2)
    cropped = pixmap.copy(left, top, side, side)
    scaled = cropped.scaled(
        size, size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    corner = max(0, size // 5 if radius is None else radius)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, corner, corner)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


def resolve_icon(
    hero_id: int | None,
    name: str,
    icon_url: str | None,
    internal_name: str | None = None,
    size: int = _ICON_SIZE,
) -> tuple[QPixmap, str | None]:
    """(пиксмап, url_для_дозагрузки | None): локальный файл -> CDN -> круг.

    Если вернулся url — вызывающий должен запросить дозагрузку через
    IconFetcher и заменить плейсхолдер по сигналу loaded.
    """
    local = scale_icon(local_hero_icon(hero_id) or QPixmap(), size)
    if not local.isNull():
        return local, None
    url = icon_url or (cdn_icon_url(internal_name) or None)
    if url:
        return placeholder_pixmap(name or "?", size), url
    return placeholder_pixmap(name or "?", size), None
