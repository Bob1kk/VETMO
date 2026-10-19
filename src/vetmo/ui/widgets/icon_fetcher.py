"""Асинхронная загрузка иконок героев через QNetworkAccessManager + кэш.

Офлайн/ошибка сети -> сигнал не приходит, карточка остаётся с плейсхолдером.
"""

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)


class IconFetcher(QObject):
    """Загружает иконки по icon_url героев (кэш по URL; один запрос на URL)."""

    loaded = Signal(str, QPixmap)  # (url, pixmap; пустой QPixmap = ошибка)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._cache: dict[str, QPixmap] = {}
        self._in_flight: set[str] = set()

    def fetch(self, url: str | None) -> None:
        """Запрашивает иконку; результат подписчики видят через loaded."""
        if not url or url in self._cache or url in self._in_flight:
            return
        self._in_flight.add(url)
        request = QNetworkRequest(QUrl(url))
        reply = self._manager.get(request)
        reply.finished.connect(lambda: self._on_finished(url, reply))

    def cached(self, url: str | None) -> QPixmap | None:
        """Иконка из кэша или None (без сети)."""
        if url is None:
            return None
        return self._cache.get(url)

    def _on_finished(self, url: str, reply: QNetworkReply) -> None:
        self._in_flight.discard(url)
        pixmap = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            if data:
                pixmap.loadFromData(data)
        reply.deleteLater()
        if not pixmap.isNull():
            self._cache[url] = pixmap
        self.loaded.emit(url, pixmap)


_fetched: IconFetcher | None = None


def icon_fetcher() -> IconFetcher:
    """Ленивый синглтон (нужен живой QApplication)."""
    global _fetched  # noqa: PLW0603
    if _fetched is None:
        _fetched = IconFetcher()
    return _fetched
