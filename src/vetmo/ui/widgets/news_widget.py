"""Левая панель лаунчера: новости патчей + бейдж «Онлайн/Офлайн»."""

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from vetmo.services.news_service import NewsItem

_DATE_ABSENT = "дата неизвестна"


class NewsWidget(QFrame):
    """Новости патчей: заголовок, бейдж сети, список новостей."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(260)

        self._badge = QLabel(self)
        self._badge.setObjectName("badgeOffline")
        self._badge.hide()

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        title = QLabel("Новости патчей", self)
        title.setObjectName("h2")
        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(self._badge)

        self._list = QListWidget(self)
        self._list.setWordWrap(False)
        self._list.setSelectionMode(
            self._list.SelectionMode.NoSelection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(header_row)
        layout.addWidget(self._list, 1)
        self.set_loading()

    # --- состояния экрана (план §9: загрузка/пусто/ошибка/нет сети) ---
    def set_loading(self) -> None:
        """Экран загрузки."""
        self._list.clear()
        self._list.addItem("⏳ Загрузка новостей…")
        self._badge.hide()

    def set_error(self, message: str) -> None:
        """Экран ошибки (worker сломался, сервис недоступен)."""
        self._list.clear()
        self._list.addItem(f"⚠ Ошибка загрузки: {message}")
        self._badge.setText("Офлайн")
        self._badge.setObjectName("badgeOffline")
        self._badge.show()

    def set_news(self, items: list[NewsItem], is_online: bool) -> None:
        """Экран данных: новости + бейдж сети."""
        self._list.clear()
        online_badge = "Онлайн" if is_online else "Офлайн"
        self._badge.setText(online_badge)
        self._badge.setObjectName(
            "badgeOnline" if is_online else "badgeOffline")
        self._badge.style().polish(self._badge)  # noqa: SLF001 — repaint hint
        self._badge.show()
        if not items:
            self._list.addItem("Новостей пока нет.\nЗапустите синхронизацию.")
            return
        for item in items:
            date = item.date or _DATE_ABSENT
            self._list.addItem(f"{date} · {item.title}\n{item.body}")

    def on_news_updated(
        self, items: list[NewsItem], is_online: bool,
    ) -> None:
        """Слот для MainViewModel.news_updated."""
        self.set_news(items, is_online)
        self._list.scrollToTop()
