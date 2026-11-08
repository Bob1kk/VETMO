"""Регрессия: кэш иконок должен переиспользоваться при пересборке UI.

Раньше ``fetch()`` молча выходил для уже закэшированного URL, а
``resolve_icon()`` не смотрел в кэш. В итоге после открытия оверлея или
кнопки «Обновить из БД» карточки показывали плейсхолдеры навсегда.
"""

from PySide6.QtGui import QColor, QPixmap

from vetmo.ui.widgets import hero_icon
from vetmo.ui.widgets.icon_fetcher import IconFetcher

_URL = "https://cdn.test/hero.png"


def _pixmap() -> QPixmap:
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor("#ff0000"))
    return pixmap


def test_fetch_emits_cached_pixmap_without_network(qapp) -> None:
    """Повторный fetch кэшированного URL отдаёт пиксмап через loaded."""
    fetcher = IconFetcher()
    pixmap = _pixmap()
    fetcher._cache[_URL] = pixmap

    received: list[tuple[str, QPixmap]] = []
    fetcher.loaded.connect(
        lambda url, loaded: received.append((url, loaded)),
    )

    fetcher.fetch(_URL)

    assert len(received) == 1
    assert received[0][0] == _URL
    assert not received[0][1].isNull()


def test_resolve_icon_uses_fetcher_cache(monkeypatch, qapp) -> None:
    """resolve_icon возвращает готовую иконку из кэша без url на дозагрузку."""
    pixmap = _pixmap()

    class _CachedFetcher:
        def cached(self, url: str | None) -> QPixmap | None:
            return pixmap if url == _URL else None

        def fetch(self, url: str | None) -> None:
            raise AssertionError("для кэша сеть не нужна")

    monkeypatch.setattr(hero_icon, "icon_fetcher", lambda: _CachedFetcher())

    resolved, request_url = hero_icon.resolve_icon(
        None, "Anti-Mage", _URL, size=16,
    )

    assert request_url is None
    assert resolved.width() == 16
    assert resolved.height() == 16


def test_resolve_icon_requests_url_when_cache_empty(monkeypatch, qapp) -> None:
    """Если кэш пуст, resolve_icon по-прежнему просит дозагрузку по URL."""
    class _EmptyFetcher:
        def cached(self, url: str | None) -> QPixmap | None:
            return None

    monkeypatch.setattr(hero_icon, "icon_fetcher", lambda: _EmptyFetcher())

    _resolved, request_url = hero_icon.resolve_icon(
        None, "Anti-Mage", _URL, size=16,
    )

    assert request_url == _URL
