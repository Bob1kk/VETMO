"""Левая панель лаунчера: новости патчей + бейдж «Онлайн/Офлайн» (R2).

Элемент = заголовок (кликабельный: QDesktopServices.openUrl) + сниппет
(до 2 строк) + дата; hover-подсветка строки. Если офлайн и список пуст —
компактный плейсхолдер «Новости недоступны (офлайн)», не пустая панель.
Обновление по таймеру зоны ответственности MainWindow (задача C R2).
"""

from html import escape

from PySide6.QtCore import Qt, QUrl
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
_SNIPPET_LIMIT = 150


class NewsRow(QFrame):
    """Строка новости: заголовок-ссылка, сниппет, дата (hover через QSS)."""

    def __init__(self, item: NewsItem, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("newsRow")
        title = str(item.title or "Патч")
        link = getattr(item, "link", None) or getattr(item, "url", None)
        self._title = QLabel(self)
        self._title.setObjectName("newsTitle")
        if link:
            url = str(link)
            self._title.setTextFormat(Qt.TextFormat.RichText)
            self._title.setText(
                f'<a href="{escape(url, quote=True)}">{escape(title)}</a>')
            self._title.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction)
            self._title.linkActivated.connect(
                lambda href: QDesktopServices.openUrl(QUrl(href)))
            self._title.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._title.setText(title)
        self._snippet = QLabel(self)
        self._snippet.setObjectName("newsSnippet")
        self._snippet.setWordWrap(True)
        body = str(item.body or "")
        if len(body) > _SNIPPET_LIMIT:
            body = body[:_SNIPPET_LIMIT].rstrip() + "…"
        self._snippet.setText(body)
        self._date = QLabel(self)
        self._date.setObjectName("mutedSmall")
        self._date.setText(str(item.date or _DATE_ABSENT))

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(self._title, 1)
        header_row.addWidget(self._date, 0)
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 6, 8, 6)
        column.setSpacing(2)
        column.addLayout(header_row)
        column.addWidget(self._snippet)


class NewsWidget(QFrame):
    """Новости патчей: заголовок с иконкой, бейдж сети, список новостей."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(260)

        self._badge = QLabel(self)
        self._badge.setObjectName("badgeOffline")
        self._badge.hide()

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        title = QLabel("НОВОСТИ ПАТЧЕЙ", self)
        title.setObjectName("sectionTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(self._badge)

        self._placeholder = QLabel(self)
        self._placeholder.setObjectName("newsPlaceholder")
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._rows_container = QFrame(self)
        self._rows_container.setObjectName("newsList")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows: list[NewsRow] = []

        scroll = QScrollArea(self)
        scroll.setObjectName("newsScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(header_row)
        layout.addWidget(self._placeholder)
        layout.addWidget(scroll, 1)
        self.set_loading()

    # --- состояния экрана (план §9: загрузка/пусто/ошибка/нет сети) ---
    def set_loading(self) -> None:
        """Экран загрузки."""
        self._clear_rows()
        self._placeholder.setText("⏳ Загрузка новостей…")
        self._placeholder.show()
        self._badge.hide()

    def set_error(self, message: str) -> None:
        """Экран ошибки (worker сломался, сервис недоступен)."""
        self._clear_rows()
        self._placeholder.setText(f"⚠ Ошибка загрузки: {message}")
        self._placeholder.show()
        self._badge.setText("Офлайн")
        self._badge.setObjectName("badgeOffline")
        self._badge.show()

    def set_news(self, items: list[NewsItem], is_online: bool) -> None:
        """Экран данных: новости + бейдж сети; офлайн -> плейсхолдер."""
        self._clear_rows()
        online_badge = "Онлайн" if is_online else "Офлайн"
        self._badge.setText(online_badge)
        self._badge.setObjectName(
            "badgeOnline" if is_online else "badgeOffline")
        self._badge.style().polish(self._badge)  # noqa: SLF001 — repaint hint
        self._badge.show()
        if not items:
            if not is_online:
                self._placeholder.setText("📡 Новости недоступны (офлайн)")
            else:
                self._placeholder.setText(
                    "Новостей пока нет.\nЗапустите синхронизацию.")
            self._placeholder.show()
            return
        self._placeholder.hide()
        for item in items:
            row = NewsRow(item, self)
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)

    def on_news_updated(
        self, items: list[NewsItem], is_online: bool,
    ) -> None:
        """Слот для MainViewModel.news_updated."""
        self.set_news(items, is_online)
        self._scroll_to_top()

    def row_count(self) -> int:
        """Количество строк новостей (для смоука/тестов)."""
        return len(self._rows)

    # --- внутренние ---
    def _clear_rows(self) -> None:
        # Удаляем и строки, и распорку addStretch: иначе при каждом
        # обновлении новостей в layout накапливались бы пустые stretch-итемы.
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
