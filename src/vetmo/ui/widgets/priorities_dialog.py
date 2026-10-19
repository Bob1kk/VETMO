"""Диалог приоритетов позиций 1..5: редактор списков героев (T-013/game-agent).

Валидирует и собирает dict[1..5] -> hero_id list; запись в БД делает
родитель через сигнал saved (worker-поток).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
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

_ACCENT = "#5B8DEF"

_POSITION_TITLES = {
    1: "Позиция 1 (керри)",
    2: "Позиция 2 (мид)",
    3: "Позиция 3 (оффлейн)",
    4: "Позиция 4 (саппорт)",
    5: "Позиция 5 (хард-саппорт)",
}

_ATTR_LABELS = {
    "str": "сила", "agi": "ловкость", "int": "интеллект",
    "all": "универсал", "universal": "универсал",
}


class PrioritiesDialog(QDialog):
    """Пять списков героев по позициям + общий поиск/добавление слева."""

    saved = Signal(object)  # dict[int, list[int]]

    def __init__(
        self,
        heroes: list[Hero],
        priorities: dict[int, list[int]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Приоритеты позиций 1–5")
        self.resize(780, 560)
        self._heroes = heroes
        self._hero_by_id = {h.id: h for h in heroes}
        self._position_lists: dict[int, QListWidget] = {}

        # Левая колонка: поиск + каталог героев
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Поиск героя…")
        self._all = QListWidget(self)
        self._all.itemDoubleClicked.connect(
            lambda _item: self._add_to_position(1))
        catalog_box = QGroupBox("Каталог героев (двойной клик — позиция 1)", self)
        catalog_layout = QVBoxLayout(catalog_box)
        catalog_layout.setContentsMargins(8, 8, 8, 8)
        catalog_layout.addWidget(self._search)
        catalog_layout.addWidget(self._all, 1)

        right = self._build_positions()

        layout = QHBoxLayout(self)
        layout.addWidget(catalog_box, 5)
        layout.addWidget(right, 7)

        buttons = QDialogButtonBox(self)
        save = buttons.addButton(
            "Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(
            "Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        save.setDefault(True)

        main = QVBoxLayout(self)
        main.addLayout(layout, 1)
        main.addWidget(buttons)

        self._search.textChanged.connect(self._refill_catalog)
        self._refill_catalog("")
        self._apply_priorities(priorities)

    # --- каталог ---
    def _refill_catalog(self, query: str) -> None:
        self._all.clear()
        lowered = (query or "").strip().lower()
        for hero in self._heroes:
            display = hero.localized_name or hero.name
            if lowered and lowered not in display.lower():
                continue
            attr = _ATTR_LABELS.get(hero.primary_attr, hero.primary_attr)
            roles = ", ".join(hero.roles[:2]) if hero.roles else "роли —"
            item = QListWidgetItem(f"{display} · {attr} · {roles}")
            item.setData(Qt.ItemDataRole.UserRole, hero.id)
            item.setToolTip(hero.name)
            self._all.addItem(item)

    def _build_positions(self) -> QWidget:
        grid_box = QGroupBox("Приоритет героев по позициям", self)
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        for position in range(1, 6):
            title = QLabel(_POSITION_TITLES[position], grid_box)
            title.setStyleSheet(f"color: {_ACCENT};")
            lst = QListWidget(grid_box)
            lst.setMaximumHeight(74)
            self._position_lists[position] = lst
            plus = QPushButton("+", grid_box)
            minus = QPushButton("−", grid_box)
            up = QPushButton("↑", grid_box)
            down = QPushButton("↓", grid_box)
            for widget in (plus, minus, up, down):
                widget.setMaximumWidth(32)
                widget.setToolTip({
                    plus: "Добавить выбранного героя из каталога",
                    minus: "Убрать выбранного героя",
                    up: "Поднять приоритет",
                    down: "Опустить приоритет",
                }[widget])
            plus.clicked.connect(lambda _=False, p=position: self._add_to_position(p))
            minus.clicked.connect(lambda _=False, p=position: self._remove_from(p))
            up.clicked.connect(lambda _=False, p=position: self._move(p, -1))
            down.clicked.connect(lambda _=False, p=position: self._move(p, 1))
            buttons_row = QHBoxLayout()
            buttons_row.addWidget(plus)
            buttons_row.addWidget(minus)
            buttons_row.addWidget(up)
            buttons_row.addWidget(down)
            grid.addWidget(title, 0, position - 1)
            grid.addWidget(lst, 1, position - 1)
            grid.addLayout(buttons_row, 2, position - 1)
        return grid_box

    # --- операции со списками позиций ---
    def _add_to_position(self, position: int) -> None:
        item = self._all.currentItem()
        if item is None:
            return
        hero_id = item.data(Qt.ItemDataRole.UserRole)
        for lst in self._position_lists.values():
            seen = self._hero_ids(lst)
            if hero_id in seen:
                lst.takeItem(seen.index(hero_id))
        display = item.text().split(" · ")[0] or f"Герой {hero_id}"
        new_item = QListWidgetItem(display)
        new_item.setData(Qt.ItemDataRole.UserRole, hero_id)
        self._position_lists[position].addItem(new_item)

    def _remove_from(self, position: int) -> None:
        lst = self._position_lists[position]
        row = lst.currentRow()
        if row >= 0:
            lst.takeItem(row)

    def _move(self, position: int, delta: int) -> None:
        lst = self._position_lists[position]
        row = lst.currentRow()
        if row < 0:
            return
        target = row + delta
        if not 0 <= target < lst.count():
            return
        item = lst.takeItem(row)
        lst.insertItem(target, item)
        lst.setCurrentRow(target)

    @staticmethod
    def _hero_ids(lst: QListWidget) -> list[int]:
        return [
            lst.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(lst.count())
        ]

    # --- сохранение ---
    def _apply_priorities(self, priorities: dict[int, list[int]]) -> None:
        for position, hero_ids in priorities.items():
            lst = self._position_lists.get(int(position))
            if lst is None:
                continue
            for hero_id in hero_ids:
                hero = self._hero_by_id.get(hero_id)
                if hero is None:
                    continue
                item = QListWidgetItem(hero.localized_name or hero.name)
                item.setData(Qt.ItemDataRole.UserRole, hero.id)
                lst.addItem(item)

    def _on_save(self) -> None:
        priorities = {
            position: self._hero_ids(lst)
            for position, lst in self._position_lists.items()
        }
        self.saved.emit(priorities)
        self.accept()
