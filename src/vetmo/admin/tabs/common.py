"""Общие помощники Admin-вкладок: форматирование, таблицы и общее состояние sync.

Модуль не содержит бизнес-логики и не ходит в сеть: только Qt-хелперы,
которые используют несколько вкладок (таблицы, JSON-viewer, форматирование
дат/чисел) и ``SyncState`` — общий флаг «идёт синхронизация», чтобы
«Обзор» и «Синхронизация» не запускали два sync одновременно.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QPlainTextEdit, QTableView

OK_COLOR = QColor("#43C59E")
DANGER_COLOR = QColor("#E35D6A")
WARNING_COLOR = QColor("#E8B05A")

_STATUS_LABELS: dict[str, str] = {
    "running": "Выполняется",
    "ok": "Успешно",
    "partial": "Частично",
    "error": "Ошибка",
}


def as_int(value: object, default: int | None = None) -> int | None:
    """Приводит значение к int; None при ошибке."""
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def as_float(value: object, default: float | None = None) -> float | None:
    """Приводит значение к float; None при ошибке."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def format_int(value: object) -> str:
    """Целое с пробелами-разделителями; прочерк для пустого значения."""
    number = as_int(value)
    if number is None:
        return "—"
    return f"{number:,}".replace(",", " ")


def format_rate(value: object) -> str:
    """Winrate/pickrate/banrate в процентах."""
    number = as_float(value)
    if number is None:
        return "—"
    return f"{number:.2f}%"


def format_delta(value: object) -> str:
    """Дельта со знаком; прочерк, если данных нет."""
    number = as_float(value)
    if number is None:
        return "—"
    return f"{number:+.2f}"


def format_datetime(value: object) -> str:
    """ISO-дата из БД -> локальное «ДД.ММ.ГГГГ ЧЧ:ММ»."""
    if value is None or value == "":
        return "—"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d.%m.%Y %H:%M")


def format_age(value: object) -> str:
    """Сколько времени прошло с момента ``value`` (для карточки свежести)."""
    if value is None or value == "":
        return "нет данных"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return "нет данных"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - parsed.astimezone(UTC)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} дн назад"


def status_text(status: object) -> str:
    """Русская подпись статуса запуска."""
    key = str(status or "").strip().lower()
    return _STATUS_LABELS.get(key, str(status or "—"))


def status_color(status: object) -> QColor:
    """Цвет статуса запуска."""
    key = str(status or "").strip().lower()
    if key == "ok":
        return OK_COLOR
    if key == "partial":
        return WARNING_COLOR
    if key == "error":
        return DANGER_COLOR
    return QColor("#8E99AD")


def pretty_json(value: object) -> str:
    """JSON с отступами; строки парсятся, ошибки не роняют UI."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def make_item(
    text: str,
    *,
    sort_value: object | None = None,
    color: QColor | None = None,
    align_right: bool = False,
) -> QStandardItem:
    """QStandardItem с отдельным значением для сортировки."""
    item = QStandardItem(text)
    item.setEditable(False)
    item.setData(sort_value if sort_value is not None else text, Qt.ItemDataRole.UserRole)
    if color is not None:
        item.setForeground(QBrush(color))
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def configure_table(table: QTableView, *, stretch_column: int = 0) -> None:
    """Единый вид таблиц: только чтение, строки, растянутая колонка."""
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)


class JsonViewer(QPlainTextEdit):
    """Только-readonly JSON-viewer с моноширинным шрифтом."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(9)
        self.setFont(font)
        self.setPlaceholderText("Здесь появится JSON-ответ…")

    def set_data(self, value: object) -> None:
        """Показывает объект или сырой текст."""
        self.setPlainText(pretty_json(value))


class SyncState(QObject):
    """Общий флаг «sync выполняется» для вкладок «Обзор» и «Синхронизация»."""

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False

    @property
    def is_busy(self) -> bool:
        """Идёт ли сейчас синхронизация."""
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Меняет состояние и уведомляет подписчиков только при изменении."""
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)


__all__ = [
    "DANGER_COLOR",
    "JsonViewer",
    "OK_COLOR",
    "SyncState",
    "WARNING_COLOR",
    "as_float",
    "as_int",
    "configure_table",
    "format_age",
    "format_datetime",
    "format_delta",
    "format_int",
    "format_rate",
    "make_item",
    "pretty_json",
    "status_color",
    "status_text",
]
