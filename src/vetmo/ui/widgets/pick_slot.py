"""Клетка доски пиков в оверлее: пустая или с выбранным героем.

Клик по клетке открывает выбор героя (диалог с фильтром по атрибутам).
Крестик убирает пик. Виджет не зависит от сервисов — только сигналы,
поэтому его легко тестировать и переиспользовать.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from vetmo.domain.models import Hero
from vetmo.ui.widgets.hero_icon import placeholder_pixmap, resolve_icon, scale_icon
from vetmo.ui.widgets.icon_fetcher import icon_fetcher

_ICON_SIZE = 24


class PickSlot(QFrame):
    """Кликабельная клетка (team, position) для ручного выбора героя."""

    clicked = Signal()
    clear_clicked = Signal()

    def __init__(
        self, team: str, position: int, parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.team = team
        self.position = int(position)
        self._hero: Hero | None = None
        self._requested_url: str | None = None

        self.setObjectName("overlaySlot")
        self.setProperty("filled", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(32)

        self._badge = QLabel(str(position), self)
        self._badge.setObjectName("overlaySlotBadge")
        self._badge.setFixedSize(16, 16)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel(self)
        self._icon.setFixedSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._name = QLabel(self)
        self._name.setObjectName("overlaySlotName")

        self._clear = QPushButton("×", self)
        self._clear.setObjectName("overlaySlotClear")
        self._clear.setFixedSize(18, 18)
        self._clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._clear.setToolTip("Убрать пик из клетки")
        self._clear.clicked.connect(self.clear_clicked.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(6)
        layout.addWidget(self._badge)
        layout.addWidget(self._icon)
        layout.addWidget(self._name, 1)
        layout.addWidget(self._clear)

        icon_fetcher().loaded.connect(self._on_icon_loaded)
        self.set_empty()

    # --- публичный API ---
    def set_empty(self) -> None:
        """Пустая клетка: «+» и подсказка «выбрать героя»."""
        self._hero = None
        self._requested_url = None
        self._icon.setPixmap(scale_icon(placeholder_pixmap("+", _ICON_SIZE), _ICON_SIZE))
        self._name.setText("Выбрать героя")
        self._clear.hide()
        self.setToolTip(
            f"{self._team_name()} · позиция {self.position}: клик — выбрать героя")
        self._set_filled(False)

    def set_hero(self, hero: Hero) -> None:
        """Заполненная клетка: иконка, имя и крестик очистки."""
        self._hero = hero
        name = hero.localized_name or hero.name
        pixmap, url = resolve_icon(hero.id, name, hero.icon_url)
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
        self._name.setText(name)
        self._clear.show()
        self.setToolTip(
            f"{self._team_name()} · позиция {self.position}: {name}. "
            "Клик — заменить героя, × — убрать.")
        self._set_filled(True)
        if url:
            self._requested_url = url
            icon_fetcher().fetch(url)

    def hero(self) -> Hero | None:
        """Текущий герой клетки (None для пустой)."""
        return self._hero

    # --- события ---
    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Левый клик по клетке — запрос выбора героя."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()
            return
        super().mousePressEvent(event)

    # --- внутренние ---
    def _team_name(self) -> str:
        return "Radiant" if self.team == "radiant" else "Dire"

    def _set_filled(self, filled: bool) -> None:
        self.setProperty("filled", filled)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def _on_icon_loaded(self, url: str, pixmap: QPixmap) -> None:
        """Подменяет плейсхолдер, когда CDN-иконка догрузилась."""
        if url != self._requested_url or pixmap.isNull():
            return
        self._requested_url = None
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
