"""Центральная панель лаунчера: мета-таблица топ-героев (TWR/Pick)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vetmo.services.news_service import MetaSummary
from vetmo.ui.widgets.icon_fetcher import icon_fetcher

_HEADERS = ("Иконка", "Герой", "WR %", "Пик %")


class MetaWidget(QFrame):
    """Мета-обзор: версия патча + таблица топ героев (win_rate/pick_rate)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        self._patch = QLabel("Мета-обзор", self)
        self._patch.setObjectName("h2")

        self._status = QLabel(self)
        self._status.setObjectName("muted")

        self._table = QTableWidget(0, len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(0, 44)
        self._icon_rows: dict[str, list[int]] = {}
        icon_fetcher().loaded.connect(self._on_icon_loaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.addWidget(self._patch)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        layout.addWidget(self._status)
        layout.addWidget(self._table, 1)
        self.set_loading()

    # --- состояния экрана ---
    def set_loading(self) -> None:
        """Экран загрузки."""
        self._status.setText("⏳ Загрузка меты…")
        self._status.show()
        self._table.setRowCount(0)
        self._table.setEnabled(False)

    def set_error(self, message: str) -> None:
        """Экран ошибки."""
        self._status.setText(f"⚠ Ошибка загрузки меты: {message}")
        self._status.show()
        self._table.setRowCount(0)
        self._table.setEnabled(False)

    def set_empty(self) -> None:
        """Пустое состояние: меты в БД нет (нужна синхронизация)."""
        self._patch.setText("Мета-обзор")
        self._status.setText(
            "Нет мета-данных. Нажмите «Синхронизировать данные».")
        self._status.show()
        self._table.setRowCount(0)

    def set_meta(self, summary: MetaSummary) -> None:
        """Экран данных: строка на каждого героя мета-топа."""
        self._patch.setText(
            f"Мета-обзор · патч {summary.patch_version or '—'}")
        self._table.setRowCount(len(summary.top))
        for row, (hero, win_rate, pick_rate) in enumerate(summary.top):
            icon_item = QTableWidgetItem()
            icon_item.setData(
                Qt.ItemDataRole.TextAlignmentRole,
                Qt.AlignmentFlag.AlignCenter,
            )
            self._table.setItem(row, 0, icon_item)
            name_item = QTableWidgetItem(hero.localized_name or hero.name)
            name_item.setToolTip(
                f"{hero.primary_attr} · {', '.join(hero.roles) or 'роли —'}")
            self._table.setItem(row, 1, name_item)
            wr_item = QTableWidgetItem(f"{win_rate:.1f}")
            wr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, wr_item)
            pick_item = QTableWidgetItem(f"{pick_rate:.1f}")
            pick_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, pick_item)
            if hero.icon_url:
                self._request_icon(row, hero.icon_url)
        self._status.hide()
        self._table.setEnabled(True)

    def on_meta_updated(self, summary: MetaSummary) -> None:
        """Слот для MainViewModel.meta_updated."""
        if summary.top:
            self.set_meta(summary)
        else:
            self.set_empty()

    # --- иконки (через общий IconFetcher, без блокировки UI) ---
    def _request_icon(self, row: int, url: str) -> None:
        self._icon_rows.setdefault(url, []).append(row)
        icon_fetcher().fetch(url)

    def _on_icon_loaded(self, url: str, pixmap) -> None:
        rows = self._icon_rows.pop(url, [])
        if pixmap.isNull():
            return
        icon = QIcon(pixmap)
        for row in rows:
            item = self._table.item(row, 0)
            if item is not None:
                item.setIcon(icon)
