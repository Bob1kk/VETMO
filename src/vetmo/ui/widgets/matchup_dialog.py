"""Диалог матчапов героя: контрпики, хорошие пики и связки.

Открывается по клику на ячейку героя в мета-таблице. Данные читаются
из Supabase в worker-потоке; в диалоге показываются три отдельных списка
по 10 строк. Малая выборка помечается только там, где она действительно
попала в десятку (надёжных строк не хватило).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vetmo.domain.matchup import MatchupEntry, MatchupReport
from vetmo.ui.widgets.hero_icon import resolve_icon, scale_icon
from vetmo.ui.workers import start_worker

_GREEN = "#43C59E"
_YELLOW = "#E8B05A"
_RED = "#E35D6A"
_MUTED = "#8E99AD"

_ICON_SIZE = 44
_ROW_ICON = 26
_ROW_HEIGHT = 34
_LOW_SAMPLE_TOOLTIP = (
    "Меньше 500 матчей: строка добавлена только потому, что надёжных "
    "матчапов не хватило до десяти."
)


def _pct(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",") + "%"


def _thousands(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _wr_color(value: float) -> str:
    if value >= 52.0:
        return _GREEN
    if value >= 50.0:
        return _YELLOW
    return _RED


class MatchupDialog(QDialog):
    """Немодальный диалог с тремя таблицами матчапов."""

    def __init__(
        self,
        *,
        hero_id: int,
        hero_name: str,
        icon_url: str | None,
        internal_name: str | None,
        rank_tier: int,
        patch_id: int | None = None,
        loader: Callable[[int, int, int | None], MatchupReport],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._hero_id = int(hero_id)
        self._hero_name = hero_name or f"Герой {hero_id}"
        self._rank_tier = int(rank_tier or 0)
        self._patch_id = patch_id
        self._loader = loader
        self._loaded = False
        self._worker: object | None = None
        self._tables: dict[str, QTableWidget] = {}
        self._tabs: dict[str, int] = {}

        self.setWindowTitle(f"Матчапы · {self._hero_name}")
        self.resize(780, 640)
        self.setMinimumSize(620, 480)

        pixmap, _url = resolve_icon(
            self._hero_id, self._hero_name, icon_url, internal_name,
            size=_ICON_SIZE,
        )
        self._icon = QLabel(self)
        self._icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))

        title = QLabel(self._hero_name, self)
        title.setObjectName("h1")
        self._subtitle = QLabel("Загружаем матчапы…", self)
        self._subtitle.setObjectName("metaSubtitle")
        self._subtitle.setWordWrap(True)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.addWidget(title)
        title_box.addWidget(self._subtitle)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self._icon)
        header.addLayout(title_box, 1)

        self._note = QLabel(self)
        self._note.setObjectName("stateInfo")
        self._note.setWordWrap(True)
        self._note.hide()

        tabs = QTabWidget(self)
        tabs.setObjectName("matchupTabs")
        self._tabs_widget = tabs
        for key, label in (
            ("counter", "Контрпики"),
            ("good", "Хорошие пики"),
            ("synergy", "Связки"),
        ):
            table = self._build_table(tabs)
            self._tables[key] = table
            self._tabs[key] = tabs.addTab(table, label)

        footer = QHBoxLayout()
        self._source = QLabel(
            "STRATZ · Ranked All Pick · все позиции", self)
        self._source.setObjectName("mutedSmall")
        close_button = QPushButton("Закрыть", self)
        close_button.setObjectName("secondary")
        close_button.clicked.connect(self.close)
        footer.addWidget(self._source, 1)
        footer.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._note)
        layout.addWidget(tabs, 1)
        layout.addLayout(footer)

        QTimer.singleShot(0, self.load)

    # ------------------------------------------------------------- таблица --
    def _build_table(self, parent: QWidget) -> QTableWidget:
        table = QTableWidget(0, 5, parent)
        table.setHorizontalHeaderLabels(("#", "ГЕРОЙ", "ВИНРЕЙТ", "МАТЧИ", ""))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setIconSize(QSize(_ROW_ICON, _ROW_ICON))
        table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 34)
        table.setColumnWidth(2, 92)
        table.setColumnWidth(3, 102)
        table.setColumnWidth(4, 26)
        return table

    # -------------------------------------------------------------- загрузка --
    def load(self) -> None:
        """Запускает чтение матчапов в QThreadPool."""
        if self._loaded:
            return
        self._note.setObjectName("stateInfo")
        self._note.setText("Загружаем матчапы из Supabase…")
        self._note.show()
        self._worker = start_worker(
            self._loader,
            self._hero_id,
            self._rank_tier,
            self._patch_id,
            on_done=self._on_loaded,
            on_fail=self._on_failed,
        )

    def _on_loaded(self, result: object) -> None:
        if not isinstance(result, MatchupReport):
            self._on_failed("некорректный ответ сервиса")
            return
        self._loaded = True
        bracket = result.bracket_label or "все ранги"
        period = result.period or "последняя полная неделя"
        self._subtitle.setText(
            f"Ranked All Pick · {period} · {bracket} · все позиции")
        self._source.setText(
            f"STRATZ · Ranked All Pick · {period} · {bracket} · все позиции")
        if result.warning:
            self._note.setObjectName("stateInfo")
            self._note.setText(result.warning)
            self._note.show()
        else:
            self._note.hide()

        for key, entries in (
            ("counter", result.counters),
            ("good", result.good_picks),
            ("synergy", result.synergies),
        ):
            self._fill(self._tables[key], entries)
            label = {
                "counter": "Контрпики",
                "good": "Хорошие пики",
                "synergy": "Связки",
            }[key]
            tab_index = self._tabs[key]
            self._tabs_widget.setTabText(
                tab_index, f"{label} · {len(entries)}")

    def _on_failed(self, message: str) -> None:
        self._note.setObjectName("stateError")
        self._note.setText(f"Не удалось загрузить матчапы: {message}")
        self._note.show()

    def _fill(
        self, table: QTableWidget, entries: list[MatchupEntry],
    ) -> None:
        table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            rank = QTableWidgetItem(str(row_index + 1))
            rank.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rank.setForeground(QColor(_MUTED))
            table.setItem(row_index, 0, rank)

            pixmap, _url = resolve_icon(
                entry.hero_id, entry.name, entry.icon_url,
                entry.internal_name, size=_ROW_ICON,
            )
            hero = QTableWidgetItem(entry.name or f"Герой {entry.hero_id}")
            hero.setIcon(QIcon(scale_icon(pixmap, _ROW_ICON)))
            hero.setToolTip(entry.internal_name or entry.name)
            table.setItem(row_index, 1, hero)

            wr = QTableWidgetItem(_pct(entry.win_rate))
            wr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            wr.setForeground(QColor(_wr_color(entry.win_rate)))
            table.setItem(row_index, 2, wr)

            matches = QTableWidgetItem(_thousands(entry.match_count))
            matches.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if not entry.sample_reliable:
                matches.setForeground(QColor(_YELLOW))
                matches.setToolTip(_LOW_SAMPLE_TOOLTIP)
            table.setItem(row_index, 3, matches)

            warning = QTableWidgetItem("⚠" if not entry.sample_reliable else "")
            warning.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            warning.setForeground(QColor(_YELLOW))
            if not entry.sample_reliable:
                warning.setToolTip(_LOW_SAMPLE_TOOLTIP)
            table.setItem(row_index, 4, warning)

    # ---------------------------------------------------------- для тестов --
    def is_loaded(self) -> bool:
        """Данные загружены (для тестов/смоука)."""
        return self._loaded

    def tab_counts(self) -> tuple[int, int, int]:
        """(контрпики, хорошие, связки) — для тестов."""
        return (
            self._tables["counter"].rowCount(),
            self._tables["good"].rowCount(),
            self._tables["synergy"].rowCount(),
        )
