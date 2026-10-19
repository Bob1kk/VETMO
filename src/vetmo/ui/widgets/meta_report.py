"""Центральная панель лаунчера: мета-отчёт в стиле dotabuff (R2, задача A).

Тулбар-чипсы фильтров (позиция 1..5, ранг Herald..Immortal) + таблица:
иконка+имя, бейджи позиций, винрейт со шкалой, дельты ▲/▼, частота пиков,
частота банов. Данные приходят из MainViewModel.meta_updated (MetaReport);
иконки — локальный кэш -> CDN -> круглый инициал-плейсхолдер.
"""

from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QHoverEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from vetmo.ui.viewmodels.main_viewmodel import (
    MetaReport,
    MetaReportRow,
    _normalize_meta_row,
)
from vetmo.ui.widgets.hero_icon import resolve_icon, scale_icon
from vetmo.ui.widgets.icon_fetcher import icon_fetcher
from vetmo.ui.widgets.matchup import format_matchup_tooltip
from vetmo.ui.workers import start_worker

_YELLOW = "#E0A458"
_GREEN = "#3FB68B"
_RED = "#E05661"
_GREY = "#8A91A0"

_ICON_SIZE = 30
_ROW_HEIGHT = 36

_COL_HERO, _COL_POS, _COL_WR, _COL_DWR, _COL_PICK, _COL_DPICK, _COL_BAN = range(7)
_HEADERS = ("Герой", "Позиции", "Винрейт", "Δ WR", "Пики", "Δ Пик", "Баны")

_POSITION_CHIPS: tuple[tuple[str, int | None], ...] = (
    ("Все", None), ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5),
)
_RANK_CHIPS: tuple[tuple[str, int | None], ...] = (
    ("Все", None), ("Herald", 1), ("Guardian", 2), ("Crusader", 3),
    ("Archon", 4), ("Legend", 5), ("Ancient", 6), ("Immortal", 7),
)


def _pct(value: float | None) -> str:
    """«52,79%» либо «—»."""
    if value is None:
        return "—"
    return f"{float(value):.2f}".replace(".", ",") + "%"


def _delta_text(value: float | None) -> tuple[str, str] | None:
    """(текст со стрелкой, цвет) или None."""
    if value is None:
        return None
    arrow = "▲" if value >= 0 else "▼"
    sign = "+" if value >= 0 else "−"
    text = f"{arrow} {sign}{abs(float(value)):.2f}".replace(".", ",") + "%"
    return text, (_GREEN if value >= 0 else _RED)


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class Bar(QWidget):
    """Горизонтальная шкала-полоска (винрейт/пики/баны) в ячейке таблицы."""

    def __init__(self, ratio: float, color: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._ratio = max(0.0, min(1.0, ratio))
        self._color = QColor(color)
        self.setMinimumHeight(7)
        self.setMaximumHeight(7)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(128, 128, 128, 56))
        painter.drawRoundedRect(track, 3, 3)
        if self._ratio > 0.0:
            width = max(4, int(track.width() * self._ratio))
            painter.setBrush(self._color)
            painter.drawRoundedRect(0, 0, width, track.height(), 3, 3)


class RateCell(QWidget):
    """Значение процента + шкала на всю ширину ячейки."""

    def __init__(
        self, value: float | None, color: str, parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        label = QLabel(_pct(value), self)
        label.setObjectName("metaRate")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 10, 0)
        row.setSpacing(8)
        row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        ratio = (value or 0.0) / 100.0 if value is not None else 0.0
        row.addWidget(Bar(ratio, color, self), 1)
        self.setFixedHeight(_ROW_HEIGHT - 6)


class DeltaCell(QLabel):
    """«▲ +1,39%» зелёный / «▼ −0,42%» красный / «—» серый."""

    def __init__(self, value: float | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("delta" if value is not None else "nodata")
        parsed = _delta_text(value)
        if parsed is None:
            self.setText("—")
        else:
            text, color = parsed
            self.setText(text)
            self.setStyleSheet(f"color: {color};")


class HeroCell(QWidget):
    """Иконка 30px + жирное имя героя; держит hero_id для тултипа."""

    def __init__(self, row: MetaReportRow, parent: QWidget) -> None:
        super().__init__(parent)
        self.hero_id = row.hero_id
        self._url: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(8)
        pixmap, url = resolve_icon(
            row.hero_id, row.name, row.icon_url, row.internal_name,
            size=_ICON_SIZE,
        )
        self._icon = QLabel(self)
        self._icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
        self._name = QLabel(row.name or f"Герой {row.hero_id}", self)
        self._name.setObjectName("metaHeroName")
        layout.addWidget(self._icon)
        layout.addWidget(self._name, 1)
        if url:
            icon_fetcher().fetch(url)
            icon_fetcher().loaded.connect(self._on_icon_loaded)
            self._url = url
        else:
            self._url = None

    def apply_icon(self, pixmap) -> None:
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))

    def _on_icon_loaded(self, url: str, pixmap) -> None:
        if url != self._url:
            return
        icon_fetcher().loaded.disconnect(self._on_icon_loaded)
        if pixmap.isNull():
            return
        self.apply_icon(pixmap)


class PositionCell(QLabel):
    """Бейджи-точки позиций: «● 1 ● 4» (из ролей/MetaRow.positions)."""

    def __init__(self, positions: list[int], parent: QWidget) -> None:
        super().__init__(parent)
        if positions:
            dots = "&nbsp;".join(
                f"<span style='color:{_GREEN}'>●</span> {position}"
                for position in positions)
            self.setText(f"<span style='font-weight:600'>{dots}</span>")
        else:
            self.setText(f"<span style='color:{_GREY}'>—</span>")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class MetaReportWidget(QFrame):
    """Мета-отчёт: чипсы фильтров + таблица топ героев (R2, задача A)."""

    filters_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._matchup_loader = None
        self._rows: list[MetaReportRow] = []
        self._row_cells: dict[int, list[QWidget]] = {}
        self._matchup_done: set[int] = set()
        self._matchup_pending: set[int] = set()

        self._patch_label = QLabel(self)
        self._patch_label.setObjectName("mutedSmall")
        self._status = QLabel(self)
        self._status.setObjectName("mutedSmall")
        self._status.setWordWrap(True)
        self._status.hide()

        self._table = self._build_table()
        self._position_group = self._build_chip_row(
            "Позиция", _POSITION_CHIPS, 0)
        self._rank_group = self._build_chip_row("Ранг", _RANK_CHIPS, 1)

        toolbar = QFrame(self)
        toolbar.setObjectName("metaToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(4)
        title_row = QHBoxLayout()
        title = QLabel("📈 МЕТА · ПАТЧ", self)
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self._patch_label)
        toolbar_layout.addLayout(title_row)
        for group in (self._position_group, self._rank_group):
            chips_row = QHBoxLayout()
            chips_row.setContentsMargins(0, 0, 0, 0)
            chips_row.setSpacing(4)
            label = QLabel(
                "Позиция:" if group is self._position_group else "Ранг:",
                self,
            )
            label.setObjectName("chipLabel")
            chips_row.addWidget(label)
            for chip in group.buttons():
                chips_row.addWidget(chip)
            chips_row.addStretch(1)
            toolbar_layout.addLayout(chips_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(toolbar)
        layout.addWidget(self._status)
        layout.addWidget(self._table, 1)
        self.set_loading()

    # ---------------------------------------------------------- таблица --
    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_HEADERS), self)
        table.setHorizontalHeaderLabels(_HEADERS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setShowGrid(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(_COL_HERO, QHeaderView.ResizeMode.Stretch)
        for column in (_COL_POS, _COL_WR, _COL_DWR, _COL_PICK, _COL_DPICK,
                       _COL_BAN):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(_COL_POS, 86)
        table.setColumnWidth(_COL_WR, 150)
        table.setColumnWidth(_COL_DWR, 76)
        table.setColumnWidth(_COL_PICK, 150)
        table.setColumnWidth(_COL_DPICK, 76)
        table.setColumnWidth(_COL_BAN, 130)
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)
        return table

    # ------------------------------------------------------------ чипсы --
    def _build_chip_row(
        self, title: str, definitions: tuple[tuple[str, int | None], ...],
        checked_index: int,
    ) -> QButtonGroup:
        """Эксклюзивный ряд чипсов; активный — заливка акцентом (QSS :checked)."""
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.setObjectName(f"chips_{title}")
        for index, (label, value) in enumerate(definitions):
            chip = QPushButton(label, self)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(index == checked_index)
            chip.setProperty("filterValue", value)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(chip, index)
        group.buttonClicked.connect(self._on_filter_clicked)
        return group

    def _on_filter_clicked(self, _button) -> None:
        self.filters_changed.emit()

    def filters(self) -> tuple[int | None, int | None]:
        """(position 1..5 | None, rank_tier 1..8 | None) — между репейками."""
        position = self._checked_value(self._position_group)
        rank = self._checked_value(self._rank_group)
        return position, rank

    @staticmethod
    def _checked_value(group: QButtonGroup) -> int | None:
        for button in group.buttons():
            if button.isChecked():
                value = button.property("filterValue")
                return value if isinstance(value, int) else None
        return None

    # ------------------------------------------------- состояния экрана --
    def set_loading(self) -> None:
        """Экран загрузки (строки не трогаем: фильтр остаётся на месте)."""
        self._status.setText("⏳ Загрузка меты…")
        self._status.show()

    def set_error(self, message: str) -> None:
        """Экран ошибки: «Синхронизация меты недоступна» + причина."""
        self._status.setText(f"Синхронизация меты недоступна ({message})")
        self._status.show()

    def set_empty(self) -> None:
        """Пустое состояние: меты в БД нет (нужна синхронизация)."""
        self._table.setRowCount(0)
        self._patch_label.setText("")
        self._status.setText("Нет мета-данных. Нажмите «Синхронизировать данные».")
        self._status.show()

    def on_meta_report(self, report: MetaReport) -> None:
        """Слот для MainViewModel.meta_updated."""
        if report.rows:
            self.set_meta(report)
        else:
            self.set_empty()

    # --- данные ---
    def set_meta(self, report: MetaReport) -> None:
        """Экран данных: строка на каждого героя мета-отчёта."""
        self._status.hide()
        version = report.patch_version
        self._patch_label.setText(f"патч {version}" if version else "патч —")
        # Нормализация: сырой MetaRow (контракт api-агента) ИЛИ старый
        # tuple (Hero, wr, pick) -> MetaReportRow с None-дефолтами.
        self._rows = [
            normalized
            for normalized in (_normalize_meta_row(row) for row in report.rows)
            if normalized is not None
        ]
        self._row_cells.clear()
        self._matchup_done.clear()
        self._matchup_pending.clear()
        self._table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            self._fill_row(index, row)
        scrollbar = self._table.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setSingleStep(24)  # плавный скролл (R2, задача D)
        if not report.rank_supported:
            rank = self.filters()[1]
            if rank is not None:
                self._status.setText(
                    "Ранговые тиры пока не поддерживаются мета-сервисом — "
                    "показан общий список.")
                self._status.show()

    def _fill_row(self, index: int, row: MetaReportRow) -> None:
        hero_cell = HeroCell(row, self._table)
        cells: list[QWidget] = [hero_cell]
        self._table.setCellWidget(index, _COL_HERO, hero_cell)
        position_cell = PositionCell(row.positions, self._table)
        self._table.setCellWidget(index, _COL_POS, position_cell)
        cells.append(position_cell)
        wr_cell = RateCell(row.win_rate, _GREEN, self._table)
        self._table.setCellWidget(index, _COL_WR, wr_cell)
        cells.append(wr_cell)
        delta_wr = DeltaCell(row.delta_win, self._table)
        delta_wr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setCellWidget(index, _COL_DWR, delta_wr)
        cells.append(delta_wr)
        pick_cell = RateCell(row.pick_rate, _YELLOW, self._table)
        self._table.setCellWidget(index, _COL_PICK, pick_cell)
        cells.append(pick_cell)
        delta_pick = DeltaCell(row.delta_pick, self._table)
        delta_pick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setCellWidget(index, _COL_DPICK, delta_pick)
        cells.append(delta_pick)
        ban_cell = RateCell(row.ban_rate, _GREY, self._table)
        self._table.setCellWidget(index, _COL_BAN, ban_cell)
        cells.append(ban_cell)
        self._row_cells[index] = cells

    # ------------------------------------------------- тултип матчапов --
    def set_matchup_loader(self, loader) -> None:
        """loader(hero_id) -> (strong, weak) | None — вызывается в worker."""
        self._matchup_loader = loader

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Hover-строка таблицы -> ленивый тултип контрпиков (задача B)."""
        if obj is self._table.viewport() and \
                event.type() == QEvent.Type.HoverMove:
            hover = cast(QHoverEvent, event)
            position = hover.position().toPoint()  # type: ignore[attr-defined]
            row = self._table.rowAt(position.y())
            self._maybe_request_matchup(row)
        return super().eventFilter(obj, event)

    def _maybe_request_matchup(self, row: int) -> None:
        if self._matchup_loader is None or not 0 <= row < len(self._rows):
            return
        row_data = self._rows[row]
        if row_data.hero_id in (self._matchup_done | self._matchup_pending):
            return
        self._matchup_pending.add(row_data.hero_id)
        start_worker(
            self._matchup_loader, row_data.hero_id,
            on_done=lambda result, index=row, name=row_data.name: (
                self._matchup_ready(index, name, result)),
            on_fail=lambda _msg, index=row: self._matchup_fail(index),
        )

    def _matchup_ready(self, index: int, name: str, result: object) -> None:
        if not 0 <= index < len(self._rows):
            return
        hero_id = self._rows[index].hero_id
        self._matchup_pending.discard(hero_id)
        self._matchup_done.add(hero_id)
        strong, weak = (result if isinstance(result, tuple) and
                        len(result) == 2 else (None, None))
        html = format_matchup_tooltip(name, strong, weak)
        self._apply_row_tooltip(index, html)

    def _matchup_fail(self, index: int) -> None:
        if 0 <= index < len(self._rows):
            self._matchup_done.add(self._rows[index].hero_id)

    def _apply_row_tooltip(self, index: int, html: str | None) -> None:
        for cell in self._row_cells.get(index, []):
            cell.setToolTip(html or "")
