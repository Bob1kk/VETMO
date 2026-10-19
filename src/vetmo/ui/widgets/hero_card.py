"""Карточка героя-рекомендации: иконка, имя, WR, причина. Контракт T-011."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from vetmo.domain.models import Hero
from vetmo.ui.widgets.icon_fetcher import icon_fetcher

_ICON_SIZE = 34

_PALETTE = (
    "#5B8DEF", "#3FB68B", "#E0A458", "#9C6FE0", "#53C7DC",
    "#E05661", "#7CB342", "#F06292", "#8D6E63", "#26A69A",
)


def placeholder_pixmap(name: str, size: int = _ICON_SIZE) -> QPixmap:
    """Цветной круг с инициалами вместо иконки (офлайн/нет URL)."""
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


class HeroCard(QFrame):
    """Карточка: [иконка 34px] Имя / WR справа / причина снизу."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("heroCard")
        self._icon = QLabel(self)
        self._icon.setFixedSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel(self)
        self._name.setObjectName("cardName")
        self._reason = QLabel(self)
        self._reason.setObjectName("cardReason")
        self._wr = QLabel(self)
        self._wr.setObjectName("cardWr")
        self._wr.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._currently_requested: str | None = None

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        info_line = QHBoxLayout()
        info_line.setContentsMargins(0, 0, 0, 0)
        info_line.addWidget(self._name, 1)
        info_line.addWidget(self._wr, 0)
        text_column.addLayout(info_line)
        text_column.addWidget(self._reason)
        top.addLayout(text_column, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addLayout(top, 1)

        icon_fetcher().loaded.connect(self._on_icon_loaded)
        self.set_empty()

    # --- публичный API ---
    def set_empty(self, message: str = "Нет рекомендаций") -> None:
        """Пустая карточка: нейтральный плейсхолдер и подпись."""
        self._apply(placeholder_pixmap("—"), "", message, "", message)
        self._currently_requested = None

    def show_hero(
        self, hero: Hero, reason: str = "", wr_text: str = "",
    ) -> None:
        """Показывает героя (иконка из сети, имя, WR, причина)."""
        pixmap = icon_fetcher().cached(hero.icon_url) if hero.icon_url else None
        self._apply(
            pixmap or placeholder_pixmap(hero.localized_name or hero.name),
            hero.localized_name or hero.name,
            reason,
            wr_text,
            reason,
        )
        if hero.icon_url:
            self._currently_requested = hero.icon_url
            icon_fetcher().fetch(hero.icon_url)

    # --- внутренние ---
    def _apply(
        self, pixmap: QPixmap, name: str, reason: str,
        wr_text: str, tooltip: str,
    ) -> None:
        icon = pixmap.scaled(
            _ICON_SIZE, _ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._icon.setPixmap(icon)
        self._name.setText(name)
        self._reason.setText(reason)
        self._wr.setText(wr_text)
        self.setToolTip(tooltip)

    def _on_icon_loaded(self, url: str, pixmap: QPixmap) -> None:
        """Обновляет иконку только своей карточки (пока URL жив)."""
        if url != self._currently_requested:
            return
        self._currently_requested = None
        if pixmap.isNull():
            return
        self._icon.setPixmap(pixmap.scaled(
            _ICON_SIZE, _ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
