"""Вкладка «Мета»: таблица vetmo_meta с фильтрами и сортировкой (T-106)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import (
    DANGER_COLOR,
    OK_COLOR,
    as_float,
    configure_table,
    format_delta,
    format_int,
    format_rate,
    make_item,
)
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_DEBOUNCE_MS = 350

_RANKS: tuple[tuple[int, str], ...] = (
    (1, "Рекрут"),
    (2, "Страж"),
    (3, "Рыцарь"),
    (4, "Герой"),
    (5, "Легенда"),
    (6, "Властелин"),
    (7, "Божество"),
    (8, "Титан"),
)

_POSITIONS: tuple[tuple[int, str], ...] = (
    (1, "1 — Керри"),
    (2, "2 — Мид"),
    (3, "3 — Оффлейн"),
    (4, "4 — Роумер"),
    (5, "5 — Поддержка"),
)

_HEADERS = (
    "Герой",
    "Winrate",
    "Pickrate",
    "Banrate",
    "Матчи",
    "Δ Winrate",
    "Δ Pickrate",
)


def _rate_color(value: object):
    """Цвет winrate: зелёный >= 52%, красный <= 48%, иначе None."""
    number = as_float(value)
    if number is None:
        return None
    if number >= 52.0:
        return OK_COLOR
    if number <= 48.0:
        return DANGER_COLOR
    return None


def _delta_color(value: object):
    """Цвет дельты: рост зелёный, падение красное."""
    number = as_float(value)
    if number is None or number == 0:
        return None
    return OK_COLOR if number > 0 else DANGER_COLOR


class MetaTab(QWidget):
    """Мета последнего патча (окно 7 дней) с фильтрами ранг/позиция/поиск."""

    status_message = Signal(str)

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._generation = 0
        self._loading = False
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_DEBOUNCE_MS)
        self._timer.timeout.connect(self.reload)
        self.reload()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Мета", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Свежий патч, окно 7 дней. «Все ранги/позиции» — агрегированный срез 0.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self._rank = QComboBox(self)
        self._rank.setObjectName("filterCombo")
        self._rank.addItem("Все ранги", 0)
        for value, label in _RANKS:
            self._rank.addItem(f"{value} — {label}", value)

        self._position = QComboBox(self)
        self._position.setObjectName("filterCombo")
        self._position.addItem("Все позиции", 0)
        for value, label in _POSITIONS:
            self._position.addItem(label, value)

        self._search = QLineEdit(self)
        self._search.setObjectName("search")
        self._search.setPlaceholderText("Поиск героя по имени…")
        self._search.setClearButtonEnabled(True)

        self._apply_button = QPushButton("Применить", self)
        self._apply_button.setObjectName("secondary")
        self._apply_button.clicked.connect(self.reload)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(QLabel("Ранг:", self))
        filters.addWidget(self._rank)
        filters.addWidget(QLabel("Позиция:", self))
        filters.addWidget(self._position)
        filters.addWidget(self._search, 1)
        filters.addWidget(self._apply_button)

        self._state = QLabel("Загрузка меты…", self)
        self._state.setObjectName("mutedSmall")

        self._model = QStandardItemModel(0, len(_HEADERS), self)
        self._model.setHorizontalHeaderLabels(list(_HEADERS))
        self._model.setSortRole(Qt.ItemDataRole.UserRole)

        self._table = QTableView(self)
        self._table.setModel(self._model)
        configure_table(self._table, stretch_column=0)
        self._table.sortByColumn(1, Qt.SortOrder.DescendingOrder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(filters)
        layout.addWidget(self._state)
        layout.addWidget(self._table, 1)

        self._rank.currentIndexChanged.connect(self._schedule)
        self._position.currentIndexChanged.connect(self._schedule)
        self._search.textChanged.connect(self._schedule)
        self._search.returnPressed.connect(self.reload)

    def _schedule(self) -> None:
        """Перезагрузка с небольшой задержкой, чтобы не дёргать сеть на каждый символ."""
        self._timer.start()

    # -------------------------------------------------------------- данные --
    def filters(self) -> tuple[int, int, str | None]:
        """Выбранные фильтры: (rank_tier, position, search)."""
        rank = int(self._rank.currentData() or 0)
        position = int(self._position.currentData() or 0)
        search = self._search.text().strip() or None
        return rank, position, search

    def reload(self) -> None:
        """Запрашивает строки меты в фоне; устаревшие ответы игнорируются."""
        self._timer.stop()
        self._generation += 1
        generation = self._generation
        self._loading = True
        self._state.setText("Загрузка меты…")
        self._state.setStyleSheet("")
        rank, position, search = self.filters()
        self.status_message.emit("Мета: читаем Supabase…")

        def done(rows: list[dict[str, Any]]) -> None:
            if generation != self._generation:
                return
            self._loading = False
            self._apply_rows(rows)
            self._state.setText(f"Загружено героев: {len(rows)} · окно 7 дней")
            self.status_message.emit(f"Мета загружена: {len(rows)} строк")

        def fail(message: str) -> None:
            if generation != self._generation:
                return
            self._loading = False
            self._clear_model()
            self._state.setText(f"Ошибка загрузки: {message}")
            self._state.setStyleSheet("color: #E35D6A;")
            self.status_message.emit(f"Мета: ошибка ({message})")

        start_worker(
            self._ctx.repository.meta_rows,
            rank,
            position,
            search,
            on_done=done,
            on_fail=fail,
        )

    def _clear_model(self) -> None:
        self._table.setSortingEnabled(False)
        self._model.removeRows(0, self._model.rowCount())
        self._table.setSortingEnabled(True)

    def _apply_rows(self, rows: list[dict[str, Any]]) -> None:
        self._table.setSortingEnabled(False)
        self._model.removeRows(0, self._model.rowCount())
        for row in rows:
            hero = str(
                row.get("hero_name")
                or row.get("localized_name")
                or row.get("hero_internal_name")
                or f"hero_{row.get('hero_id', '—')}"
            )
            win = as_float(row.get("win_rate"))
            pick = as_float(row.get("pick_rate"))
            ban = as_float(row.get("ban_rate"))
            matches = row.get("match_count")
            self._model.appendRow(
                [
                    make_item(hero, sort_value=hero.casefold()),
                    make_item(
                        format_rate(win),
                        sort_value=win if win is not None else -1.0,
                        color=_rate_color(win),
                        align_right=True,
                    ),
                    make_item(
                        format_rate(pick),
                        sort_value=pick if pick is not None else -1.0,
                        align_right=True,
                    ),
                    make_item(
                        format_rate(ban),
                        sort_value=ban if ban is not None else -1.0,
                        align_right=True,
                    ),
                    make_item(
                        format_int(matches),
                        sort_value=matches or 0,
                        align_right=True,
                    ),
                    make_item(
                        format_delta(row.get("delta_win")),
                        sort_value=as_float(row.get("delta_win"), -999.0),
                        color=_delta_color(row.get("delta_win")),
                        align_right=True,
                    ),
                    make_item(
                        format_delta(row.get("delta_pick")),
                        sort_value=as_float(row.get("delta_pick"), -999.0),
                        color=_delta_color(row.get("delta_pick")),
                        align_right=True,
                    ),
                ]
            )
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(1, Qt.SortOrder.DescendingOrder)

    # ------------------------------------------------------------ служебное --
    def row_count(self) -> int:
        """Число строк в модели (для смоук-тестов)."""
        return self._model.rowCount()

    def state_text(self) -> str:
        """Текст состояния (для смоук-тестов)."""
        return self._state.text()

    def shutdown(self) -> None:
        """Таймер не должен срабатывать после закрытия окна."""
        self._timer.stop()


__all__ = ["MetaTab"]
