"""Диалог выбора героя для клетки оверлея.

Фильтр по атрибутам (сила/ловкость/интеллект/универсал) + поиск по имени.
Диалог самостоятельный: вызывающая сторона получает `hero_selected(hero_id)`
и сама решает, как записать пик.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.domain.models import Hero
from vetmo.ui.widgets.hero_icon import resolve_icon, scale_icon
from vetmo.ui.widgets.icon_fetcher import icon_fetcher

_ICON_SIZE = 24

_ATTR_FILTERS: tuple[tuple[str, str | None], ...] = (
    ("Все", None),
    ("Сила", "str"),
    ("Ловкость", "agi"),
    ("Интеллект", "int"),
    ("Универсал", "all"),
)

_ATTR_LABELS = {
    "str": "сила",
    "agi": "ловкость",
    "int": "интеллект",
    "all": "универсал",
    "universal": "универсал",
}

_URL_ROLE = Qt.ItemDataRole.UserRole + 1


class HeroPickDialog(QDialog):
    """Список героев с фильтром по атрибуту и поиском."""

    hero_selected = Signal(int)

    def __init__(
        self,
        heroes: list[Hero],
        team: str,
        position: int,
        current_hero_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._heroes = sorted(
            heroes, key=lambda hero: (hero.localized_name or hero.name).lower())
        self._attr: str | None = None

        team_name = "Radiant" if team == "radiant" else "Dire"
        self.setWindowTitle(f"Пик — {team_name}, позиция {position}")
        self.setMinimumSize(420, 540)

        title = QLabel(f"{team_name} · позиция {position}", self)
        title.setObjectName("h2")
        subtitle = QLabel(
            "Выберите героя. Список можно отфильтровать по атрибуту.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str | None, QPushButton] = {}
        for label, attr in _ATTR_FILTERS:
            button = QPushButton(label, self)
            button.setObjectName("chip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                lambda _checked=False, value=attr: self._set_attr(value))
            self._filter_group.addButton(button)
            filter_row.addWidget(button)
            self._filter_buttons[attr] = button
        self._filter_buttons[None].setChecked(True)
        filter_row.addStretch(1)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Поиск героя…")
        self._search.setClearButtonEnabled(True)

        self._list = QListWidget(self)
        self._list.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._list.setAlternatingRowColors(False)
        self._list.itemDoubleClicked.connect(lambda _item: self._submit())

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена", self)
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        self._submit_button = QPushButton("Выбрать", self)
        self._submit_button.setObjectName("primary")
        self._submit_button.clicked.connect(self._submit)
        buttons.addWidget(cancel)
        buttons.addWidget(self._submit_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(filter_row)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)

        icon_fetcher().loaded.connect(self._on_icon_loaded)
        self._search.textChanged.connect(self._refill)
        self._refill()

        if current_hero_id is not None:
            self._select_hero(int(current_hero_id))

    # --- публичный API ---
    def visible_hero_ids(self) -> list[int]:
        """Id героев, прошедших текущий фильтр (для тестов/отладки)."""
        ids: list[int] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def set_attribute_filter(self, attr: str | None) -> None:
        """Программно переключает фильтр атрибута."""
        self._set_attr(attr)

    # --- внутренние ---
    def _set_attr(self, attr: str | None) -> None:
        self._attr = attr
        button = self._filter_buttons.get(attr)
        if button is not None:
            button.setChecked(True)
        self._refill()

    def _refill(self) -> None:
        query = self._search.text().strip().lower()
        self._list.clear()
        for hero in self._heroes:
            if self._attr is not None:
                attr = hero.primary_attr.lower()
                if attr != self._attr and not (
                    self._attr == "all" and attr == "universal"
                ):
                    continue
            display = hero.localized_name or hero.name
            if query and query not in display.lower():
                continue
            pixmap, url = resolve_icon(hero.id, display, hero.icon_url)
            attr_label = _ATTR_LABELS.get(
                hero.primary_attr.lower(), hero.primary_attr)
            item = QListWidgetItem(
                QIcon(scale_icon(pixmap, _ICON_SIZE)),
                f"{display} · {attr_label}",
            )
            item.setData(Qt.ItemDataRole.UserRole, hero.id)
            if url:
                item.setData(_URL_ROLE, url)
                icon_fetcher().fetch(url)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _select_hero(self, hero_id: int) -> None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            if int(item.data(Qt.ItemDataRole.UserRole)) == hero_id:
                self._list.setCurrentRow(index)
                return

    def _submit(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        hero_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.hero_selected.emit(hero_id)
        self.accept()

    def _on_icon_loaded(self, url: str, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        icon = QIcon(scale_icon(pixmap, _ICON_SIZE))
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(_URL_ROLE) == url:
                item.setIcon(icon)


__all__ = ["HeroPickDialog"]
