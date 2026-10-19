"""Диалог ручного ввода пика ради 1..5 — fallback к CV (T-013).

Команда берётся автоматически из правил 2-2-1 (rules.team_for_step),
позиция — по suggest_position, если выбрано «Авто». add_pick_auto
вызывает MainWindow в worker-потоке; результат диалог показывает методов
show_state()/on_fail().
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.domain.models import DraftSession, Hero
from vetmo.domain.rules import TOTAL_PICKS

_TEAM_RU = {"radiant": "Radiant", "dire": "Dire"}

_ATTR_LABELS = {
    "str": "сила", "agi": "ловкость", "int": "интеллект",
    "all": "универсал", "universal": "универсал",
}


class ManualPickDialog(QDialog):
    """Поиск + список героев, авто-команда/позиция, ручной пик."""

    pick_requested = Signal(object, int)  # (position | None, hero_id)

    def __init__(
        self,
        heroes: list[Hero],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ручной ввод пика")
        self.resize(360, 520)
        self._heroes = heroes
        self._busy = False

        self._state_label = QLabel("Драфт: …", self)
        self._state_label.setObjectName("h2")
        self._state_label.setWordWrap(True)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Поиск героя…")

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(
            lambda _item: self._submit())

        position_row = QHBoxLayout()
        self._position = QComboBox(self)
        self._position.addItem("Позиция: авто", None)
        for value in range(1, 6):
            self._position.addItem(f"Позиция: {value}", value)
        self._submit_button = QPushButton("Подтвердить пик", self)
        self._submit_button.setObjectName("primary")
        self._submit_button.clicked.connect(self._submit)
        position_row.addWidget(self._position, 1)
        position_row.addWidget(self._submit_button)

        close_row = QHBoxLayout()
        self._note = QLabel("", self)
        self._note.setObjectName("muted")
        close_row.addWidget(self._note, 1)
        close_button = QPushButton("Закрыть", self)
        close_button.setObjectName("secondary")
        close_button.clicked.connect(self.reject)
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._state_label)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)
        layout.addLayout(position_row)
        layout.addLayout(close_row)

        self._search.textChanged.connect(self._refill)
        self._refill("")

    # --- данные ---
    def show_state(self, state: DraftSession) -> None:
        """Обновляет индикатор шага/команды (работает и после пика)."""
        self._busy = False
        self._submit_button.setEnabled(True)
        if state.current_step >= TOTAL_PICKS:
            self._state_label.setText(
                f"Драфт завершён: {state.current_step}/{state.total_picks}")
            self._submit_button.setEnabled(False)
            return
        from vetmo.domain.rules import team_for_step  # noqa: PLC0415
        team = team_for_step(state.current_step)
        self._state_label.setText(
            f"Шаг {state.current_step + 1}/{state.total_picks} — "
            f"пикает {_TEAM_RU[team]}. Шаг: {state.current_step}. "
            "Команда выбирается автоматически (2-2-1).")

    def show_heroes(self, heroes: list[Hero]) -> None:
        """Загружает каталог героев (worker -> UI)."""
        self._heroes = heroes
        self._refill(self._search.text())

    def on_fail(self, message: str) -> None:
        """Ошибка добавления пика (нет сети/герой пикнут/шаг вышел)."""
        self._busy = False
        self._submit_button.setEnabled(True)
        self._note.setText(message)
        QMessageBox.warning(self, "Пик не принят", message)

    # --- внутренние ---
    def _refill(self, query: str) -> None:
        self._list.clear()
        lowered = (query or "").strip().lower()
        for hero in self._heroes:
            display = hero.localized_name or hero.name
            if lowered and lowered not in display.lower():
                continue
            attr = _ATTR_LABELS.get(hero.primary_attr, hero.primary_attr)
            roles = ", ".join(hero.roles[:2]) if hero.roles else "роли —"
            item = QListWidgetItem(f"{display} · {attr} · {roles}")
            item.setData(Qt.ItemDataRole.UserRole, hero.id)
            self._list.addItem(item)

    def _submit(self) -> None:
        if self._busy:
            return
        item = self._list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Нет выбора", "Выберите героя из списка.")
            return
        hero_id = int(item.data(Qt.ItemDataRole.UserRole))
        position = self._position.currentData()
        self._busy = True
        self._submit_button.setEnabled(False)
        self._note.setText("Записываем пик…")
        self.pick_requested.emit(position, hero_id)
