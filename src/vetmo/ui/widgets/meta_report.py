"""Центральная панель лаунчера: мета героев OpenDota.

Структура: заголовок с патчем, сводные карточки, поиск/сортировка, фильтры
по позиции и рангу, таблица всех героев. Данные приходят из
``MainViewModel.meta_updated``; иконки — локальный кэш -> CDN -> плейсхолдер.

Важно про источники: win/pick — публичные матчи OpenDota, pro-баны — только
общий срез (у OpenDota нет разбивки банов по рангам). Позиции — эвристика
по ролям героя, а не турнирная статистика.
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QHoverEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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

_GREEN = "#43C59E"
_YELLOW = "#E8B05A"
_RED = "#E35D6A"
_GREY = "#8E99AD"

_ICON_SIZE = 36
_ROW_HEIGHT = 52

_COL_RANK, _COL_HERO, _COL_POS, _COL_WR, _COL_DWR, _COL_PICK, _COL_DPICK, _COL_BAN = range(8)
_HEADERS = (
    "#", "ГЕРОЙ", "ПОЗИЦИИ", "ВИНРЕЙТ", "Δ WR", "ПИКИ", "Δ ПИК", "PRO-БАНЫ",
)

_POSITION_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Все позиции", -1), ("Позиция 1", 1), ("Позиция 2", 2),
    ("Позиция 3", 3), ("Позиция 4", 4), ("Позиция 5", 5),
)
_RANK_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Все ранги", -1), ("Herald", 1), ("Guardian", 2), ("Crusader", 3),
    ("Archon", 4), ("Legend", 5), ("Ancient", 6), ("Divine", 7),
    ("Immortal", 8),
)
_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Винрейт ↓", "win"), ("Пики ↓", "pick"), ("Pro-баны ↓", "ban"),
    ("Имя A–Z", "name"),
)
_ATTR_LABELS = {"str": "STR", "agi": "AGI", "int": "INT", "all": "UNIV"}


def _pct(value: float | None) -> str:
    """«52,79%» либо «—»."""
    if value is None:
        return "—"
    return f"{float(value):.2f}".replace(".", ",") + "%"


def _delta_text(value: float | None) -> str:
    """«▲ +1,39%» / «▼ −0,42%» / «—»."""
    if value is None:
        return "—"
    arrow = "▲" if value >= 0 else "▼"
    sign = "+" if value >= 0 else "−"
    return f"{arrow} {sign}{abs(float(value)):.2f}".replace(".", ",") + "%"


def _hero_word(count: int) -> str:
    """Русское склонение «герой/героя/героев»."""
    if count % 10 == 1 and count % 100 != 11:
        return "герой"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "героя"
    return "героев"


def _wr_color(value: float | None) -> str:
    if value is None:
        return _GREY
    if value >= 52.0:
        return _GREEN
    if value >= 50.0:
        return _YELLOW
    return _RED


class Bar(QWidget):
    """Горизонтальная шкала-полоска (винрейт/пики/баны) в ячейке таблицы."""

    def __init__(self, ratio: float, color: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._ratio = max(0.0, min(1.0, ratio))
        self._color = QColor(color)
        self.setFixedHeight(4)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(128, 128, 128, 46))
        painter.drawRoundedRect(track, 2, 2)
        if self._ratio > 0.0:
            width = max(3, int(track.width() * self._ratio))
            painter.setBrush(self._color)
            painter.drawRoundedRect(0, 0, width, track.height(), 2, 2)


class RateCell(QWidget):
    """Значение процента + шкала; прозрачный фон для чередования строк."""

    def __init__(
        self, value: float | None, color: str, parent: QWidget,
        tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        label = QLabel(_pct(value), self)
        label.setObjectName("metaRate")
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        ratio = (value or 0.0) / 100.0 if value is not None else 0.0
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 7, 10, 7)
        column.setSpacing(5)
        column.addWidget(label)
        column.addWidget(Bar(ratio, color, self))
        if tooltip:
            self.setToolTip(tooltip)
            label.setToolTip(tooltip)


class DeltaCell(QLabel):
    """«▲ +1,39%» / «▼ −0,42%» / «—» с темозависимым цветом."""

    def __init__(self, value: float | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if value is None:
            self.setObjectName("nodata")
        else:
            self.setObjectName("deltaPos" if value >= 0 else "deltaNeg")
        self.setText(_delta_text(value))


class PositionCell(QWidget):
    """Компактные бейджи позиций 1..5 (максимум 3 + «+N»)."""

    def __init__(self, positions: list[int], parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 4, 0)
        row.setSpacing(3)
        if not positions:
            empty = QLabel("—", self)
            empty.setObjectName("nodata")
            row.addWidget(empty)
        else:
            for position in positions[:3]:
                badge = QLabel(str(position), self)
                badge.setObjectName("posBadge")
                badge.setFixedSize(21, 21)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setToolTip(f"Позиция {position} по ролям (эвристика)")
                row.addWidget(badge)
            if len(positions) > 3:
                more = QLabel(f"+{len(positions) - 3}", self)
                more.setObjectName("mutedSmall")
                more.setToolTip(
                    "Все позиции: " + ", ".join(map(str, positions)))
                row.addWidget(more)
        row.addStretch(1)


class HeroCell(QWidget):
    """Иконка 36px + имя + атрибут/тип атаки; держит hero_id для тултипа."""

    def __init__(
        self, row: MetaReportRow, parent: QWidget,
        on_hover: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hero_id = row.hero_id
        self._url: str | None = None
        self._on_hover = on_hover
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(9)
        pixmap, url = resolve_icon(
            row.hero_id, row.name, row.icon_url, row.internal_name,
            size=_ICON_SIZE,
        )
        self._icon = QLabel(self)
        self._icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(0)
        self._name = QLabel(row.name or f"Герой {row.hero_id}", self)
        self._name.setObjectName("metaHeroName")
        self._attr = QLabel(
            self._subtitle(row.primary_attr, row.attack_type), self)
        self._attr.setObjectName("heroAttr")
        text_column.addWidget(self._name)
        text_column.addWidget(self._attr)
        layout.addWidget(self._icon)
        layout.addLayout(text_column, 1)
        if url:
            icon_fetcher().fetch(url)
            icon_fetcher().loaded.connect(self._on_icon_loaded)
            self._url = url

    @staticmethod
    def _subtitle(primary_attr: str, attack_type: str) -> str:
        attr = _ATTR_LABELS.get((primary_attr or "").lower(), primary_attr.upper())
        attack = (attack_type or "").upper()
        return " · ".join(part for part in (attr, attack) if part) or "DOTA 2"

    def apply_icon(self, pixmap) -> None:
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))

    def _on_icon_loaded(self, url: str, pixmap) -> None:
        if url != self._url:
            return
        try:
            icon_fetcher().loaded.disconnect(self._on_icon_loaded)
        except (RuntimeError, TypeError):
            pass
        self._url = None
        if pixmap.isNull():
            return
        self.apply_icon(pixmap)

    def enterEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._on_hover is not None:
            self._on_hover(self.hero_id)
        super().enterEvent(event)


class MetaReportWidget(QFrame):
    """Мета-отчёт: сводка, поиск/сортировка, фильтры и таблица героев."""

    filters_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metaPanel")
        self._matchup_loader = None
        self._all_rows: list[MetaReportRow] = []
        self._view_rows: list[MetaReportRow] = []
        self._row_cells: dict[int, list[QWidget]] = {}
        self._matchup_done: set[int] = set()
        self._matchup_pending: set[int] = set()
        self._rank_supported = True

        self._patch_label = QLabel("ПАТЧ —", self)
        self._patch_label.setObjectName("patchPill")
        self._source_label = QLabel("OPENDOTA · PUBLIC MATCHES", self)
        self._source_label.setObjectName("mutedSmall")
        self._source_label.setToolTip(
            "Винрейт и пики — публичные матчи OpenDota. Pro-баны — отдельный "
            "pro-срез, доступный только в общем срезе и не разбитый по рангам.")

        self._status = QLabel(self)
        self._status.setObjectName("stateInfo")
        self._status.setWordWrap(True)
        self._status.hide()

        self._table = self._build_table()
        self._position = self._build_combo(_POSITION_OPTIONS, "Позиция")
        self._rank = self._build_combo(_RANK_OPTIONS, "Ранг")
        self._sort = self._build_combo(_SORT_OPTIONS, "Сортировка")
        self._search = QLineEdit(self)
        self._search.setObjectName("search")
        self._search.setPlaceholderText("Поиск героя…")
        self._search.setClearButtonEnabled(True)
        self._reset_button = QPushButton("Сбросить", self)
        self._reset_button.setObjectName("tiny")
        self._count_label = QLabel(self)
        self._count_label.setObjectName("countLabel")

        self._stat_heroes = self._build_stat("ГЕРОЕВ В СРЕЗЕ")
        self._stat_wr = self._build_stat("СРЕДНИЙ WR")
        self._stat_leader = self._build_stat("ЛИДЕР ПО WR")
        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(8)
        for card in (self._stat_heroes, self._stat_wr, self._stat_leader):
            stats.addWidget(card, 1)

        toolbar = QFrame(self)
        toolbar.setObjectName("metaToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Мета героев", self)
        title.setObjectName("metaTitle")
        subtitle = QLabel(
            "Винрейт и пики — public, pro-баны — отдельный pro-срез", self)
        subtitle.setObjectName("metaSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
        title_row.addWidget(self._source_label)
        title_row.addWidget(self._patch_label)
        toolbar_layout.addLayout(title_row)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(self._search, 3)
        controls.addWidget(self._position, 1)
        controls.addWidget(self._rank, 1)
        controls.addWidget(self._sort, 1)
        controls.addWidget(self._reset_button, 0)
        toolbar_layout.addLayout(controls)
        toolbar_layout.addLayout(stats)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(toolbar)
        layout.addWidget(self._status)
        layout.addWidget(self._table, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        footer.addWidget(self._count_label)
        footer.addStretch(1)
        source_note = QLabel(
            "Позиции — эвристика · Δ — к прошлой синхронизации · "
            "pro-баны не по рангам",
            self,
        )
        source_note.setObjectName("mutedSmall")
        footer.addWidget(source_note)
        layout.addLayout(footer)

        self._search.textChanged.connect(self._apply_view)
        self._sort.currentIndexChanged.connect(self._apply_view)
        self._position.currentIndexChanged.connect(self._on_server_filter)
        self._rank.currentIndexChanged.connect(self._on_server_filter)
        self._reset_button.clicked.connect(self._reset_filters)
        self.set_loading()

    # ---------------------------------------------------------- таблица --
    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_HEADERS), self)
        table.setObjectName("metaTable")
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
        table.setMinimumWidth(760)
        header = table.horizontalHeader()
        header.setSectionResizeMode(_COL_HERO, QHeaderView.ResizeMode.Stretch)
        for column in (
            _COL_RANK, _COL_POS, _COL_WR, _COL_DWR, _COL_PICK, _COL_DPICK,
            _COL_BAN,
        ):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(_COL_RANK, 36)
        table.setColumnWidth(_COL_POS, 88)
        table.setColumnWidth(_COL_WR, 142)
        table.setColumnWidth(_COL_DWR, 70)
        table.setColumnWidth(_COL_PICK, 132)
        table.setColumnWidth(_COL_DPICK, 70)
        table.setColumnWidth(_COL_BAN, 108)
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)
        return table

    # ------------------------------------------------------ управление --
    def _build_combo(
        self, options: tuple[tuple[str, object], ...], accessible: str,
    ) -> QComboBox:
        combo = QComboBox(self)
        combo.setObjectName("filterCombo")
        combo.setAccessibleName(accessible)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for label, value in options:
            combo.addItem(label, value)
        return combo

    @staticmethod
    def _build_stat(label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        value = QLabel("—")
        value.setObjectName("statValue")
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        column = QVBoxLayout(card)
        column.setContentsMargins(10, 7, 10, 7)
        column.setSpacing(0)
        column.addWidget(value)
        column.addWidget(caption)
        card._value_label = value  # type: ignore[attr-defined]
        return card

    def _on_server_filter(self) -> None:
        self.filters_changed.emit()

    def _reset_filters(self) -> None:
        for combo in (self._position, self._rank):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._sort.blockSignals(True)
        self._sort.setCurrentIndex(0)
        self._sort.blockSignals(False)
        self._search.clear()
        self.filters_changed.emit()

    def filters(self) -> tuple[int | None, int | None]:
        """(position 1..5 | None, rank_tier 1..8 | None)."""
        position = self._position.currentData()
        rank = self._rank.currentData()
        return (
            None if not isinstance(position, int) or position < 1 else position,
            None if not isinstance(rank, int) or rank < 1 else rank,
        )

    def search_text(self) -> str:
        """Текст поиска (для тестов/смоука)."""
        return self._search.text()

    def row_count(self) -> int:
        """Количество видимых строк (для тестов)."""
        return len(self._view_rows)

    # ------------------------------------------------- состояния экрана --
    def _set_state(self, text: str, error: bool = False) -> None:
        self._status.setObjectName("stateError" if error else "stateInfo")
        self._status.setText(text)
        self._status.show()
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def set_loading(self) -> None:
        """Экран загрузки: старые строки не трогаем, показываем статус."""
        self._set_state("Обновляем мета-данные OpenDota…")

    def set_error(self, message: str) -> None:
        """Ошибка загрузки; последние успешные строки остаются на экране."""
        self._set_state(f"Мета недоступна ({message})", error=True)

    def set_empty(self) -> None:
        """Пустое состояние: в БД нет среза."""
        self._all_rows = []
        self._view_rows = []
        self._table.setRowCount(0)
        self._patch_label.setText("ПАТЧ —")
        self._count_label.setText("Нет данных")
        self._update_stats([])
        self._set_state(
            "Нет мета-данных. Нажмите «Синхронизировать данные» в настройках.")

    def on_meta_report(self, report: MetaReport) -> None:
        """Слот для MainViewModel.meta_updated."""
        if report.rows:
            self.set_meta(report)
        else:
            self.set_empty()

    # --- данные ---
    def set_meta(self, report: MetaReport) -> None:
        """Экран данных: все строки среза, затем клиентская фильтрация."""
        self._rank_supported = report.rank_supported
        version = report.patch_version
        self._patch_label.setText(
            f"ПАТЧ {version.upper()}" if version else "ПАТЧ —")
        normalized = (
            _normalize_meta_row(row) for row in report.rows
        )
        self._all_rows = []
        seen: set[int] = set()
        for row in normalized:
            if row is None or row.hero_id in seen:
                continue
            seen.add(row.hero_id)
            self._all_rows.append(row)
        self._source_label.setToolTip(
            "Винрейт и пики — публичные матчи OpenDota (метка патча "
            f"{version or 'не определена'}). Pro-баны — отдельный pro-срез "
            "OpenDota; он доступен только в общем срезе и может не совпадать "
            "с патчем public-матчей."
        )
        if not report.rank_supported:
            self._set_state(
                "Ранговые тиры пока не поддерживаются мета-сервисом — "
                "показан общий список.")
        else:
            self._status.hide()
        self._apply_view()

    def _apply_view(self) -> None:
        """Поиск/сортировка поверх загруженного среза."""
        query = self._search.text().strip().lower().replace("_", " ")
        rows = list(self._all_rows)
        if query:
            rows = [
                row for row in rows
                if query in row.name.lower().replace("_", " ")
                or query in (row.internal_name or "").lower().replace("_", " ")
            ]
        sort_key = self._sort.currentData()
        if sort_key == "pick":
            rows.sort(
                key=lambda row: (
                    -(row.pick_rate if row.pick_rate is not None else -1.0),
                    row.name.lower(),
                ))
        elif sort_key == "ban":
            rows.sort(
                key=lambda row: (
                    -(row.ban_rate if row.ban_rate is not None else -1.0),
                    row.name.lower(),
                ))
        elif sort_key == "name":
            rows.sort(key=lambda row: row.name.lower())
        else:
            rows.sort(
                key=lambda row: (
                    -(row.win_rate if row.win_rate is not None else -1.0),
                    -(row.pick_rate if row.pick_rate is not None else -1.0),
                    row.name.lower(),
                ))
        self._view_rows = rows
        self._populate_table()
        self._update_stats(rows)
        total = len(self._all_rows)
        if query or len(rows) != total:
            self._count_label.setText(
                f"{len(rows)} из {total} {_hero_word(total)}")
        else:
            self._count_label.setText(f"{total} {_hero_word(total)}")

    def _populate_table(self) -> None:
        self._row_cells.clear()
        self._matchup_done.clear()
        self._matchup_pending.clear()
        self._table.setRowCount(len(self._view_rows))
        for index, row in enumerate(self._view_rows):
            self._fill_row(index, row)
        scrollbar = self._table.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setSingleStep(24)

    def _fill_row(self, index: int, row: MetaReportRow) -> None:
        rank_label = QLabel(f"{index + 1:02d}", self._table)
        rank_label.setObjectName("mutedSmall")
        rank_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rank_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._table.setCellWidget(index, _COL_RANK, rank_label)
        cells: list[QWidget] = [rank_label]

        hero_cell = HeroCell(
            row, self._table,
            on_hover=self._maybe_request_matchup,
        )
        self._table.setCellWidget(index, _COL_HERO, hero_cell)
        cells.append(hero_cell)

        position_cell = PositionCell(row.positions, self._table)
        self._table.setCellWidget(index, _COL_POS, position_cell)
        cells.append(position_cell)

        wr_cell = RateCell(
            row.win_rate, _wr_color(row.win_rate), self._table,
            tooltip="Винрейт публичных матчей OpenDota",
        )
        self._table.setCellWidget(index, _COL_WR, wr_cell)
        cells.append(wr_cell)

        delta_wr = DeltaCell(row.delta_win, self._table)
        self._table.setCellWidget(index, _COL_DWR, delta_wr)
        cells.append(delta_wr)

        pick_cell = RateCell(
            row.pick_rate, _YELLOW, self._table,
            tooltip="Доля матчей, в которых герой выбран (10 пиков на игру)",
        )
        self._table.setCellWidget(index, _COL_PICK, pick_cell)
        cells.append(pick_cell)

        delta_pick = DeltaCell(row.delta_pick, self._table)
        self._table.setCellWidget(index, _COL_DPICK, delta_pick)
        cells.append(delta_pick)

        rank_filter = self.filters()[1]
        ban_value = row.ban_rate if rank_filter is None else None
        if ban_value is None:
            ban_empty = QLabel("—", self._table)
            ban_empty.setObjectName("nodata")
            ban_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ban_empty.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground)
            ban_empty.setToolTip(
                "Pro-баны недоступны для рангового среза: OpenDota не "
                "разбивает их по рангам.")
            ban_cell: QWidget = ban_empty
        else:
            ban_cell = RateCell(
                ban_value, _GREY, self._table,
                tooltip="Pro-баны OpenDota: ban / (pick + ban) в pro-сцене",
            )
        self._table.setCellWidget(index, _COL_BAN, ban_cell)
        cells.append(ban_cell)
        self._row_cells[row.hero_id] = cells

        rank_supported_note = (
            "" if self._rank_supported or rank_filter is None
            else " · выбранный ранг не поддерживается — общий срез")
        for cell in cells:
            if not cell.toolTip() and rank_supported_note:
                cell.setToolTip(rank_supported_note.lstrip(" ·"))

    def _update_stats(self, rows: list[MetaReportRow]) -> None:
        heroes = self._stat_heroes._value_label  # type: ignore[attr-defined]
        average = self._stat_wr._value_label  # type: ignore[attr-defined]
        leader = self._stat_leader._value_label  # type: ignore[attr-defined]
        heroes.setText(str(len(rows)))
        rates = [
            row.win_rate for row in rows if row.win_rate is not None
        ]
        average.setText(_pct(sum(rates) / len(rates)) if rates else "—")
        if rows:
            best = max(
                rows,
                key=lambda row: row.win_rate if row.win_rate is not None else -1.0,
            )
            leader.setText(best.name or "—")
            leader.setToolTip(
                f"{best.name}: {_pct(best.win_rate)} винрейт в текущем срезе")
        else:
            leader.setText("—")
            leader.setToolTip("")

    # ------------------------------------------------- тултип матчапов --
    def set_matchup_loader(self, loader) -> None:
        """loader(hero_id) -> (strong, weak) | None — вызывается в worker."""
        self._matchup_loader = loader

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Hover по таблице -> ленивый тултип контрпиков."""
        if obj is self._table.viewport() and \
                event.type() == QEvent.Type.HoverMove:
            hover = cast(QHoverEvent, event)
            position = hover.position().toPoint()  # type: ignore[attr-defined]
            row = self._table.rowAt(position.y())
            if 0 <= row < len(self._view_rows):
                self._maybe_request_matchup(self._view_rows[row].hero_id)
        return super().eventFilter(obj, event)

    def _maybe_request_matchup(self, hero_id: int) -> None:
        if self._matchup_loader is None:
            return
        if hero_id in (self._matchup_done | self._matchup_pending):
            return
        row = next(
            (item for item in self._view_rows if item.hero_id == hero_id),
            None,
        )
        if row is None:
            return
        self._matchup_pending.add(hero_id)
        start_worker(
            self._matchup_loader, hero_id,
            on_done=lambda result, hid=hero_id, name=row.name: (
                self._matchup_ready(hid, name, result)),
            on_fail=lambda _msg, hid=hero_id: self._matchup_fail(hid),
        )

    def _matchup_ready(self, hero_id: int, name: str, result: object) -> None:
        self._matchup_pending.discard(hero_id)
        self._matchup_done.add(hero_id)
        strong, weak = (result if isinstance(result, tuple) and
                        len(result) == 2 else (None, None))
        html = format_matchup_tooltip(name, strong, weak)
        if html:
            self._apply_row_tooltip(hero_id, html)

    def _matchup_fail(self, hero_id: int) -> None:
        self._matchup_pending.discard(hero_id)
        self._matchup_done.add(hero_id)

    def _apply_row_tooltip(self, hero_id: int, html: str) -> None:
        for cell in self._row_cells.get(hero_id, []):
            cell.setToolTip(html)
