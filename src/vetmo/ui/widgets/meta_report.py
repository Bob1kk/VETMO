"""Центральная панель лаунчера: мета героев (через Supabase).

Структура: сводные карточки, поиск/сортировка, фильтры по позиции и рангу,
таблица всех героев. Данные приходят из ``MainViewModel.meta_updated``;
иконки — локальный кэш -> CDN -> плейсхолдер.

Метрики считает sync-скрипт и складывает в Supabase; в UI приходят уже
готовые значения. ``positions`` — только популярные позиции героя
(доля пиков выше порога), ``position_details`` — доля пиков/WR/матчи для
тултипа. Если деталей нет, подсказка не выдумывает источник.
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

from vetmo.domain.matchup import MatchupReport
from vetmo.ui.viewmodels.main_viewmodel import (
    MetaReport,
    MetaReportRow,
    _normalize_meta_row,
)
from vetmo.ui.widgets.hero_icon import resolve_icon, scale_icon
from vetmo.ui.widgets.icon_fetcher import icon_fetcher
from vetmo.ui.widgets.matchup import format_matchup_tooltip
from vetmo.ui.widgets.matchup_dialog import MatchupDialog
from vetmo.ui.workers import start_worker

_GREEN = "#43C59E"
_YELLOW = "#E8B05A"
_RED = "#E35D6A"
_GREY = "#8E99AD"

_ICON_SIZE = 36
_ROW_HEIGHT = 52

_COL_RANK, _COL_HERO, _COL_POS, _COL_WR, _COL_DWR, _COL_PICK, _COL_BAN = range(7)
_HEADERS = (
    "#", "ГЕРОЙ", "ПОЗИЦИИ", "ВИНРЕЙТ", "ИЗМЕНЕНИЕ", "ПИКИ", "БАНЫ",
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
    ("Винрейт ↓", "win"), ("Пики ↓", "pick"), ("Баны ↓", "ban"),
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


def _as_number(value: object) -> float | None:
    """Число из любого источника (None, str, Decimal) либо None."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_count(value: object) -> int | None:
    number = _as_number(value)
    return int(number) if number is not None else None


def _short_pct(value: float, digits: int = 1) -> str:
    """«54,2%» / «72%» — без лишних нулей после запятой."""
    text = f"{float(value):.{digits}f}".replace(".", ",")
    if digits and text.endswith(",0"):
        text = text[:-2]
    return text + "%"


def _thousands(value: int) -> str:
    """«12 340» — пробел как разделитель тысяч."""
    return f"{int(value):,}".replace(",", " ")


def _detail_value(details: object, position: int, key: str) -> object:
    """Значение из ``position_details`` (dict[int, PositionStat] и dict-строки)."""
    if not isinstance(details, dict):
        return None
    entry = details.get(position)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _position_tooltip(position: int, details: object) -> str:
    """Тултип бейджа: доля пиков/WR/матчи, если детали пришли из данных."""
    share = _as_number(_detail_value(details, position, "pick_share"))
    win_rate = _as_number(_detail_value(details, position, "win_rate"))
    matches = _as_count(_detail_value(details, position, "match_count"))
    if share is None and win_rate is None and matches is None:
        return f"Позиция {position} · популярная позиция героя в срезе"
    parts = [f"Позиция {position}"]
    if share is not None:
        parts.append(f"{_short_pct(share, 0)} пиков героя")
    if win_rate is not None:
        parts.append(f"WR {_short_pct(win_rate)}")
    if matches is not None:
        parts.append(f"{_thousands(matches)} матчей")
    return " · ".join(parts)


_BAN_SCOPE_LABELS = {
    "HERALD_GUARDIAN": "Herald–Guardian",
    "CRUSADER_ARCHON": "Crusader–Archon",
    "LEGEND_ANCIENT": "Legend–Ancient",
    "DIVINE_IMMORTAL": "Divine–Immortal",
    "ALL": "все ранги",
}


def _ban_tooltip(ban_scope: object) -> str:
    """Тултип банов: доля матчей, где герой забанен, + группа рангов."""
    base = "Доля матчей, где герой забанен"
    if not ban_scope:
        return base
    scope = str(ban_scope)
    label = _BAN_SCOPE_LABELS.get(scope.upper(), scope)
    return f"{base} · срез {label}"


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
    """Компактные бейджи популярных позиций 1..5 (максимум 3 + «+N»).

    Если ``sample_reliable=False`` — показывает предупреждение о малой
    выборке (метрика может быть неточной).
    """

    def __init__(
        self, positions: list[int], parent: QWidget,
        details: object | None = None,
        sample_reliable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 4, 0)
        row.setSpacing(3)
        ordered = self._ordered(positions, details)
        if not ordered:
            empty = QLabel("—", self)
            empty.setObjectName("nodata")
            empty.setToolTip(
                "Нет популярных позиций в выбранном срезе")
            row.addWidget(empty)
        else:
            for position in ordered[:3]:
                badge = QLabel(str(position), self)
                badge.setObjectName("posBadge")
                badge.setFixedSize(21, 21)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setToolTip(_position_tooltip(position, details))
                row.addWidget(badge)
            if len(ordered) > 3:
                more = QLabel(f"+{len(ordered) - 3}", self)
                more.setObjectName("mutedSmall")
                hidden = ordered[3:]
                more.setToolTip(
                    "Ещё позиции: " + ", ".join(
                        _position_tooltip(position, details)
                        for position in hidden))
                row.addWidget(more)
        if not sample_reliable:
            hint = QLabel("⚠", self)
            hint.setObjectName("mutedSmall")
            hint.setToolTip(
                "Малая выборка — метрика может быть неточной "
                "(меньше 50 матчей за окно)")
            row.addWidget(hint)
        row.addStretch(1)

    @staticmethod
    def _ordered(positions: list[int], details: object | None) -> list[int]:
        """Популярные позиции; при наличии деталей — по доле пиков."""
        ordered = [int(p) for p in positions]
        if not isinstance(details, dict) or not details:
            return ordered
        ordered.sort(
            key=lambda position: (
                _as_number(_detail_value(details, position, "pick_share"))
                is None,
                -(_as_number(_detail_value(details, position, "pick_share"))
                  or 0.0),
                position,
            ),
        )
        return ordered


class HeroCell(QWidget):
    """Иконка 36px + имя + атрибут/тип атаки; клик открывает матчапы."""

    clicked = Signal(int)

    def __init__(
        self, row: MetaReportRow, parent: QWidget,
        on_hover: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hero_id = row.hero_id
        self._url: str | None = None
        self._on_hover = on_hover
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Нажмите, чтобы открыть матчапы героя")
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

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.hero_id)
        super().mouseReleaseEvent(event)


class MetaReportWidget(QFrame):
    """Мета-отчёт: сводка, поиск/сортировка, фильтры и таблица героев."""

    filters_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metaPanel")
        self._matchup_loader = None
        self._matchup_details_loader: (
            Callable[[int, int, int | None], MatchupReport] | None
        ) = None
        self._matchup_dialog: MatchupDialog | None = None
        self._all_rows: list[MetaReportRow] = []
        self._view_rows: list[MetaReportRow] = []
        self._row_cells: dict[int, list[QWidget]] = {}
        self._matchup_done: set[int] = set()
        self._matchup_pending: set[int] = set()
        self._rank_supported = True

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

        self._stat_wr = self._build_stat("СРЕДНИЙ WR")
        self._stat_leader = self._build_stat("ЛИДЕР ПО WR")
        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(8)
        for card in (self._stat_wr, self._stat_leader):
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
        self._subtitle = QLabel("Ranked All Pick · последние 7 дней", self)
        self._subtitle.setObjectName("metaSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(self._subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
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
            _COL_RANK, _COL_POS, _COL_WR, _COL_DWR, _COL_PICK,
            _COL_BAN,
        ):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(_COL_RANK, 36)
        table.setColumnWidth(_COL_POS, 88)
        table.setColumnWidth(_COL_WR, 142)
        table.setColumnWidth(_COL_DWR, 112)
        table.setColumnWidth(_COL_PICK, 120)
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
        self._set_state("Обновляем мета-данные…")

    def set_error(self, message: str) -> None:
        """Ошибка загрузки; последние успешные строки остаются на экране."""
        self._set_state(f"Мета недоступна ({message})", error=True)

    def set_empty(self) -> None:
        """Пустое состояние: для среза нет строк в источнике."""
        self._all_rows = []
        self._view_rows = []
        self._table.setRowCount(0)
        self._count_label.setText("Нет данных")
        self._update_stats([])
        self._set_state(
            "Для выбранного среза данных пока нет. "
            "Обновите данные в настройках.")

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
        if report.period:
            self._subtitle.setText(f"Ranked All Pick · {report.period}")
        else:
            self._subtitle.setText("Ranked All Pick · последние 7 дней")
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
        hero_cell.clicked.connect(self._open_matchups)
        self._table.setCellWidget(index, _COL_HERO, hero_cell)
        cells.append(hero_cell)

        position_cell = PositionCell(
            row.positions, self._table,
            getattr(row, "position_details", None),
            getattr(row, "sample_reliable", True),
        )
        self._table.setCellWidget(index, _COL_POS, position_cell)
        cells.append(position_cell)

        wr_cell = RateCell(
            row.win_rate, _wr_color(row.win_rate), self._table,
            tooltip="Винрейт героя в выбранном срезе",
        )
        self._table.setCellWidget(index, _COL_WR, wr_cell)
        cells.append(wr_cell)

        delta_wr = DeltaCell(row.delta_win, self._table)
        delta_wr.setToolTip("Изменение винрейта по сравнению с предыдущим окном")
        self._table.setCellWidget(index, _COL_DWR, delta_wr)
        cells.append(delta_wr)

        pick_cell = RateCell(
            row.pick_rate, _YELLOW, self._table,
            tooltip="Доля матчей, в которых герой выбран",
        )
        self._table.setCellWidget(index, _COL_PICK, pick_cell)
        cells.append(pick_cell)

        rank_filter = self.filters()[1]
        ban_value = row.ban_rate
        ban_scope = getattr(row, "ban_scope", None)
        if ban_value is None:
            ban_empty = QLabel("—", self._table)
            ban_empty.setObjectName("nodata")
            ban_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ban_empty.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground)
            ban_empty.setToolTip("Баны для этого среза пока недоступны")
            ban_cell: QWidget = ban_empty
        else:
            ban_cell = RateCell(
                ban_value, _GREY, self._table,
                tooltip=_ban_tooltip(ban_scope),
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
        average = self._stat_wr._value_label  # type: ignore[attr-defined]
        leader = self._stat_leader._value_label  # type: ignore[attr-defined]
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

    def set_matchup_details_loader(
        self,
        loader: Callable[[int, int, int | None], MatchupReport] | None,
    ) -> None:
        """loader(hero_id, rank_tier, patch_id) -> MatchupReport."""
        self._matchup_details_loader = loader

    def _open_matchups(self, hero_id: int) -> None:
        """Клик по герою: открыть диалог контрпиков/связок."""
        if self._matchup_details_loader is None:
            return
        row = next(
            (item for item in self._view_rows if item.hero_id == hero_id),
            None,
        )
        if row is None:
            return
        if self._matchup_dialog is not None:
            self._matchup_dialog.close()
            self._matchup_dialog.deleteLater()
        rank_tier = self.filters()[1] or 0
        dialog = MatchupDialog(
            hero_id=row.hero_id,
            hero_name=row.name,
            icon_url=row.icon_url,
            internal_name=row.internal_name,
            rank_tier=rank_tier,
            loader=self._matchup_details_loader,
            parent=self.window(),
        )
        self._matchup_dialog = dialog
        dialog.show()
        dialog.raise_()

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
