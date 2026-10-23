"""Вкладка «История»: журнал vetmo_sync_runs и детали запуска (T-109)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import (
    JsonViewer,
    as_int,
    configure_table,
    format_datetime,
    format_int,
    make_item,
    status_color,
    status_text,
)
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_HEADERS = (
    "ID",
    "Начат",
    "Завершён",
    "Статус",
    "Источник",
    "Патч",
    "Мета",
    "Матчапы",
    "Ошибка",
)


def _parsed_details(value: object) -> object:
    """jsonb может прийти строкой — показываем объект, если получилось."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class RunsTab(QWidget):
    """История запусков sync с панелью деталей выбранной записи."""

    status_message = Signal(str)

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._generation = 0
        self._rows: dict[int, dict[str, Any]] = {}
        self._build_ui()
        self.refresh()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("История запусков", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Последние 100 записей vetmo_sync_runs. Выберите строку, чтобы "
            "увидеть details (jsonb) и текст ошибки.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self._refresh_button = QPushButton("Обновить", self)
        self._refresh_button.setObjectName("secondary")
        self._refresh_button.clicked.connect(self.refresh)
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        toolbar.addWidget(self._refresh_button)

        self._state = QLabel("Загрузка истории…", self)
        self._state.setObjectName("mutedSmall")

        self._model = QStandardItemModel(0, len(_HEADERS), self)
        self._model.setHorizontalHeaderLabels(list(_HEADERS))
        self._model.setSortRole(Qt.ItemDataRole.UserRole)

        self._table = QTableView(self)
        self._table.setModel(self._model)
        configure_table(self._table, stretch_column=8)
        self._table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)

        self._details = JsonViewer(self)
        self._details.setPlaceholderText("Детали запуска появятся здесь…")

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._table)
        details_box = QWidget(splitter)
        details_layout = QVBoxLayout(details_box)
        details_layout.setContentsMargins(0, 8, 0, 0)
        details_layout.setSpacing(4)
        details_title = QLabel("Детали выбранного запуска", details_box)
        details_title.setObjectName("sectionTitle")
        details_layout.addWidget(details_title)
        details_layout.addWidget(self._details, 1)
        splitter.addWidget(details_box)
        splitter.setSizes([420, 260])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(self._state)
        layout.addWidget(splitter, 1)

    # -------------------------------------------------------------- данные --
    def refresh(self) -> None:
        """Читает историю в фоне; ошибка остаётся в статус-лейбле."""
        self._generation += 1
        generation = self._generation
        self._state.setStyleSheet("")
        self._state.setText("Загрузка истории…")
        self._refresh_button.setEnabled(False)
        self.status_message.emit("История: читаем vetmo_sync_runs…")

        def done(rows: list[dict[str, Any]]) -> None:
            if generation != self._generation:
                return
            self._refresh_button.setEnabled(True)
            self._apply_rows(rows)
            self._state.setText(f"Записей: {len(rows)}")
            self.status_message.emit(f"История загружена: {len(rows)} записей")

        def fail(message: str) -> None:
            if generation != self._generation:
                return
            self._refresh_button.setEnabled(True)
            self._state.setText(f"Ошибка загрузки истории: {message}")
            self._state.setStyleSheet("color: #E35D6A;")
            self.status_message.emit(f"История: ошибка ({message})")

        start_worker(
            self._ctx.repository.list_runs,
            100,
            on_done=done,
            on_fail=fail,
        )

    def _apply_rows(self, rows: list[dict[str, Any]]) -> None:
        self._table.setSortingEnabled(False)
        self._model.removeRows(0, self._model.rowCount())
        self._rows.clear()
        for row in rows:
            row_id = as_int(row.get("id"))
            if row_id is not None:
                self._rows[row_id] = row
            status = row.get("status")
            error = str(row.get("error") or "")
            self._model.appendRow(
                [
                    make_item(
                        format_int(row_id) if row_id is not None else "—",
                        sort_value=row_id if row_id is not None else -1,
                        align_right=True,
                    ),
                    make_item(
                        format_datetime(row.get("started_at")),
                        sort_value=str(row.get("started_at") or ""),
                    ),
                    make_item(
                        format_datetime(row.get("finished_at")),
                        sort_value=str(row.get("finished_at") or ""),
                    ),
                    make_item(
                        status_text(status),
                        sort_value=status_text(status).casefold(),
                        color=status_color(status),
                    ),
                    make_item(
                        str(row.get("trigger_source") or row.get("source") or "—"),
                        sort_value=str(row.get("trigger_source") or row.get("source") or ""),
                    ),
                    make_item(str(row.get("patch_version") or "—")),
                    make_item(
                        format_int(row.get("rows_meta")),
                        sort_value=as_int(row.get("rows_meta")) or 0,
                        align_right=True,
                    ),
                    make_item(
                        format_int(row.get("rows_matchups")),
                        sort_value=as_int(row.get("rows_matchups")) or 0,
                        align_right=True,
                    ),
                    make_item(error or "—", sort_value=error.casefold()),
                ]
            )
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        if rows:
            self._table.selectRow(0)
        else:
            self._details.setPlainText("Запусков пока нет.")

    # -------------------------------------------------------------- детали --
    def _on_selection(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        item = self._model.item(indexes[0].row(), 0)
        if item is None:
            return
        row_id = as_int(item.data(Qt.ItemDataRole.UserRole))
        row = self._rows.get(row_id) if row_id is not None else None
        if row is None:
            return
        payload = {
            "id": row.get("id"),
            "status": row.get("status"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "trigger_source": row.get("trigger_source"),
            "request_id": row.get("request_id"),
            "patch_version": row.get("patch_version"),
            "rows_meta": row.get("rows_meta"),
            "rows_matchups": row.get("rows_matchups"),
            "details": _parsed_details(row.get("details")),
        }
        if row.get("error"):
            payload["error"] = row["error"]
        self._details.set_data(payload)

    # ------------------------------------------------------------ служебное --
    def row_count(self) -> int:
        """Число строк таблицы (для смоук-тестов)."""
        return self._model.rowCount()

    def shutdown(self) -> None:
        """Загрузка идёт через QThreadPool; отменять нечего."""


__all__ = ["RunsTab"]
