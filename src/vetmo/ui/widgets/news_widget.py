"""Левая панель лаунчера: новости патчей (R2)."""

from datetime import datetime
from email.utils import parsedate_to_datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vetmo.services.news_service import NewsItem

_DATE_ABSENT = ""
_SNIPPET_LIMIT = 85

# Словарь для перевода месяцев на русский
_MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"
}

def _format_date(date_str: str) -> str:
    """Переводит дату из формата Wed, 07 Oct 2026 00:22:41 +0000 в 07 окт 2026, 00:22."""
    if not date_str:
        return ""
    try:
        # Парсим стандартный формат почты/RSS
        dt = parsedate_to_datetime(date_str)
        return f"{dt.day} {_MONTHS_RU[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"
    except Exception:
        try:
            # На случай, если дата придет в формате ISO
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return f"{dt.day} {_MONTHS_RU[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"
        except Exception:
            return date_str


class NewsRow(QFrame):
    """Строка новости: вся карточка кликабельна."""

    clicked = Signal(str)

    def __init__(self, item: NewsItem, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("newsRow")

        self._link = getattr(item, "link", None) or getattr(item, "url", None)
        if self._link:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        title = str(item.title or "Патч")

        # Заголовок (теперь без HTML-ссылок, так как кликабельна вся карточка)
        self._title = QLabel(self)
        self._title.setObjectName("newsTitle")
        self._title.setWordWrap(True)
        self._title.setText(title)
        # Пропускаем клики мыши сквозь текст, чтобы срабатывал QFrame
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._snippet = QLabel(self)
        self._snippet.setObjectName("newsSnippet")
        self._snippet.setWordWrap(True)
        self._snippet.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        body = str(item.body or "")
        if len(body) > _SNIPPET_LIMIT:
            truncated = body[:_SNIPPET_LIMIT].rsplit(' ', 1)[0]
            body = truncated + "…"
        self._snippet.setText(body)

        # Дата (с переводом)
        self._date = QLabel(self)
        self._date.setObjectName("mutedSmall")
        self._date.setText(_format_date(str(item.date or "")))
        self._date.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(self._title, 1)
        header_row.addWidget(self._date, 0)

        column = QVBoxLayout(self)
        column.setContentsMargins(8, 6, 24, 6)
        column.setSpacing(2)
        column.addLayout(header_row)
        column.addWidget(self._snippet)

    def mouseReleaseEvent(self, event) -> None:
        """Обрабатываем клик по всей площади карточки."""
        if event.button() == Qt.MouseButton.LeftButton and self._link:
            self.clicked.emit(self._link)
        super().mouseReleaseEvent(event)


class NewsWidget(QFrame):
    """Новости патчей: заголовок и список карточек."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(260)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        header_row.addStretch(1)

        self._placeholder = QLabel(self)
        self._placeholder.setObjectName("newsPlaceholder")
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._rows_container = QFrame(self)
        self._rows_container.setObjectName("newsList")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._rows: list[NewsRow] = []

        scroll = QScrollArea(self)
        scroll.setObjectName("newsScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(header_row)
        layout.addWidget(self._placeholder)
        layout.addWidget(scroll, 1)
        self.set_loading()

    def set_loading(self) -> None:
        self._clear_rows()
        self._placeholder.setToolTip("")
        self._placeholder.setText("Загрузка новостей…")
        self._placeholder.show()

    def set_error(self, message: str = "") -> None:
        self._clear_rows()
        self._placeholder.setText("Не удалось обновить новости. Попробуем позже.")
        self._placeholder.setToolTip(str(message or ""))
        self._placeholder.show()

    def set_news(self, items: list[NewsItem], is_online: bool | None = None) -> None:
        self._clear_rows()
        self._placeholder.setToolTip("")
        if not items:
            self._placeholder.setText("Новостей пока нет.")
            self._placeholder.show()
            return
        self._placeholder.hide()
        for item in items:
            row = NewsRow(item, self)
            row.clicked.connect(self._open_link)
            self._rows.append(row)
            self._rows_layout.addWidget(row)

    def on_news_updated(self, items: list[NewsItem], is_online: bool | None = None) -> None:
        self.set_news(items, is_online)
        self._scroll_to_top()

    def row_count(self) -> int:
        return len(self._rows)

    def _open_link(self, url: str) -> None:
        """Открывает ссылку в браузере."""
        QDesktopServices.openUrl(QUrl(url))

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

    def _scroll_to_top(self) -> None:
        scroll = self.findChild(QScrollArea, "newsScroll")
        if scroll is not None:
            scroll.verticalScrollBar().setValue(0)
