"""Вкладка «Матчапы»: контрпики, хорошие пики и связки героя (T-107)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import (
    DANGER_COLOR,
    OK_COLOR,
    WARNING_COLOR,
    as_float,
    as_int,
    configure_table,
    format_int,
    format_rate,
    make_item,
)
from vetmo.domain.rank_brackets import BASIC_BRACKETS, basic_bracket_label
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_MIN_MATCHES = 500

_BUCKETS: tuple[tuple[str, str], ...] = (
    ("counter", "КОНТРПИКИ"),
    ("good", "ХОРОШИЕ ПИКИ"),
    ("synergy", "СВЯЗКИ"),
)

_HEADERS = ("#", "Герой", "Winrate", "Матчи", "Срез", "Выборка")


def _win_color(value: object):
    number = as_float(value)
    if number is None:
        return None
    if number >= 52.0:
        return OK_COLOR
    if number <= 48.0:
        return DANGER_COLOR
    return None


class _BucketPanel(QFrame):
    """Панель одной корзины матчапов с таблицей."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        label = QLabel(title, self)
        label.setObjectName("sectionTitle")
        self.model = QStandardItemModel(0, len(_HEADERS), self)
        self.model.setHorizontalHeaderLabels(list(_HEADERS))
        self.model.setSortRole(Qt.ItemDataRole.UserRole)
        self.table = QTableView(self)
        self.table.setModel(self.model)
        configure_table(self.table, stretch_column=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addWidget(label)
        layout.addWidget(self.table, 1)

    def clear(self) -> None:
        """Очищает таблицу."""
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        self.table.setSortingEnabled(True)

    def set_rows(self, rows: list[dict[str, Any]], names: dict[int, str]) -> None:
        """Заполняет таблицу строками одной корзины."""
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        for row in rows:
            other_id = as_int(row.get("vs_hero_id")) or 0
            other = names.get(other_id) or f"hero_{other_id}"
            win = as_float(row.get("win_rate"))
            matches = as_int(row.get("match_count")) or 0
            reliable = row.get("sample_reliable", True)
            small = (not bool(reliable)) or matches < _MIN_MATCHES
            bracket = basic_bracket_label(row.get("rank_bracket"))
            rank = as_int(row.get("bucket_rank"))
            self.model.appendRow(
                [
                    make_item(
                        format_int(rank) if rank is not None else "—",
                        sort_value=rank if rank is not None else 999,
                        align_right=True,
                    ),
                    make_item(other, sort_value=other.casefold()),
                    make_item(
                        format_rate(win),
                        sort_value=win if win is not None else -1.0,
                        color=_win_color(win),
                        align_right=True,
                    ),
                    make_item(
                        format_int(matches),
                        sort_value=matches,
                        align_right=True,
                    ),
                    make_item(bracket, sort_value=bracket.casefold()),
                    make_item(
                        "малая" if small else "—",
                        sort_value=0 if small else 1,
                        color=WARNING_COLOR if small else None,
                    ),
                ]
            )
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)


class MatchupsTab(QWidget):
    """Выбор героя и три top-10 среза из ``vetmo_hero_matchups``."""

    status_message = Signal(str)

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._hero_names: dict[int, str] = {}
        self._cache: dict[int, list[dict[str, Any]]] = {}
        self._generation = 0
        self._auto_bracket_done = False
        self._build_ui()
        self._load_heroes()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Матчапы", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Контрпики, хорошие пики и связки последнего патча. "
            "«Малая» — выборка меньше 500 матчей.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self._hero = QComboBox(self)
        self._hero.setObjectName("filterCombo")
        self._hero.setMinimumWidth(220)
        self._hero.setEnabled(False)

        self._bracket = QComboBox(self)
        self._bracket.setObjectName("filterCombo")
        self._bracket.addItem("Все ранги (ALL)", "ALL")
        for bracket in BASIC_BRACKETS:
            self._bracket.addItem(basic_bracket_label(bracket), bracket)

        self._refresh_button = QPushButton("Обновить", self)
        self._refresh_button.setObjectName("secondary")
        self._refresh_button.setToolTip("Перечитать матчапы выбранного героя")
        self._refresh_button.clicked.connect(self._force_reload)

        self._state = QLabel("Загрузка каталога героев…", self)
        self._state.setObjectName("mutedSmall")

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Герой:", self))
        controls.addWidget(self._hero)
        controls.addWidget(QLabel("Срез:", self))
        controls.addWidget(self._bracket)
        controls.addStretch(1)
        controls.addWidget(self._refresh_button)

        self._panels: dict[str, _BucketPanel] = {}
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        for key, label in _BUCKETS:
            panel = _BucketPanel(label, splitter)
            self._panels[key] = panel
            splitter.addWidget(panel)
        splitter.setSizes([400, 400, 400])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(controls)
        layout.addWidget(self._state)
        layout.addWidget(splitter, 1)

        self._hero.currentIndexChanged.connect(self._on_hero_changed)
        self._bracket.currentIndexChanged.connect(self._render)

    # -------------------------------------------------------------- герои --
    def _load_heroes(self) -> None:
        self.status_message.emit("Матчапы: читаем каталог героев…")

        def done(rows: list[dict[str, Any]]) -> None:
            self._hero.blockSignals(True)
            self._hero.clear()
            self._hero_names.clear()
            for row in rows:
                hero_id = as_int(row.get("id"))
                if hero_id is None:
                    continue
                name = str(row.get("localized_name") or row.get("name") or hero_id)
                self._hero_names[hero_id] = name
                self._hero.addItem(name, hero_id)
            self._hero.blockSignals(False)
            self._hero.setEnabled(bool(rows))
            self._refresh_button.setEnabled(bool(rows))
            if not rows:
                self._state.setText(
                    "Каталог героев пуст: сначала выполните sync или проверьте БД."
                )
                self.status_message.emit("Матчапы: каталог героев пуст")
                return
            self._state.setText(f"Героев в каталоге: {len(rows)}")
            self._on_hero_changed()

        def fail(message: str) -> None:
            self._state.setText(f"Не удалось загрузить героев: {message}")
            self._state.setStyleSheet("color: #E35D6A;")
            self.status_message.emit(f"Матчапы: ошибка каталога ({message})")

        start_worker(self._ctx.repository.heroes, on_done=done, on_fail=fail)

    def _on_hero_changed(self) -> None:
        hero_id = as_int(self._hero.currentData())
        if hero_id is None:
            return
        self._auto_bracket_done = False
        self._load_matchups(hero_id, force=False)

    def _force_reload(self) -> None:
        hero_id = as_int(self._hero.currentData())
        if hero_id is None:
            return
        self._auto_bracket_done = False
        self._load_matchups(hero_id, force=True)

    # ------------------------------------------------------------ матчапы --
    def _load_matchups(self, hero_id: int, *, force: bool) -> None:
        self._generation += 1
        generation = self._generation
        self._state.setStyleSheet("")
        if not force and hero_id in self._cache:
            self._render()
            return
        self._state.setText("Загрузка матчапов…")
        self.status_message.emit("Матчапы: читаем Supabase…")

        def done(rows: list[dict[str, Any]]) -> None:
            if generation != self._generation:
                return
            self._cache[hero_id] = rows
            self._render()
            self.status_message.emit(f"Матчапы загружены: {len(rows)} строк")

        def fail(message: str) -> None:
            if generation != self._generation:
                return
            self._cache.pop(hero_id, None)
            for panel in self._panels.values():
                panel.clear()
            self._state.setText(f"Ошибка загрузки матчапов: {message}")
            self._state.setStyleSheet("color: #E35D6A;")
            self.status_message.emit(f"Матчапы: ошибка ({message})")

        start_worker(
            self._ctx.repository.matchups,
            hero_id,
            on_done=done,
            on_fail=fail,
        )

    def _render(self) -> None:
        """Группирует строки по bucket и текущему ранговому срезу."""
        hero_id = as_int(self._hero.currentData())
        rows = self._cache.get(hero_id or -1, [])
        bracket = self._bracket.currentData()
        selected = [row for row in rows if str(row.get("rank_bracket")) == str(bracket)]
        if (
            not selected
            and rows
            and str(bracket) == "ALL"
            and not self._auto_bracket_done
        ):
            # Данных для ALL нет — переключаемся на первый доступный срез.
            available = {
                str(row.get("rank_bracket")) for row in rows if row.get("rank_bracket")
            }
            if available:
                self._auto_bracket_done = True
                index = self._bracket.findData(next(iter(sorted(available))))
                if index >= 0:
                    self._bracket.setCurrentIndex(index)
                    return
        self._auto_bracket_done = True

        grouped: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in _BUCKETS}
        for row in selected:
            bucket = str(row.get("bucket") or "")
            if bucket in grouped:
                grouped[bucket].append(row)
        for key, items in grouped.items():
            items.sort(
                key=lambda row: (
                    as_int(row.get("bucket_rank")) is None,
                    as_int(row.get("bucket_rank")) or 999,
                )
            )
            self._panels[key].set_rows(items[:10], self._hero_names)

        hero_name = self._hero.currentText() or f"hero_{hero_id}"
        self._state.setStyleSheet("")
        self._state.setText(
            f"{hero_name} · срез {basic_bracket_label(str(bracket))} · "
            f"строк: {len(selected)}"
        )

    # ------------------------------------------------------------ служебное --
    def hero_options(self) -> int:
        """Количество героев в выборе (для смоук-тестов)."""
        return self._hero.count()

    def state_text(self) -> str:
        """Текущий текст состояния (для смоук-тестов)."""
        return self._state.text()

    def shutdown(self) -> None:
        """Загрузки идут через QThreadPool; дополнительных ресурсов нет."""


__all__ = ["MatchupsTab"]
