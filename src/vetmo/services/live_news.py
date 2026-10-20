"""Живые новости Steam RSS + мета-сводка из Supabase.

Новости всегда тянутся из сети; кэш только в памяти на час. Никакого
бейджа online/offline в UI нет. При сбое сети возвращается последний
успешный ответ (если был), иначе пустой список.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from vetmo.infra.config import Settings
from vetmo.infra.http_client import build_http_client
from vetmo.services.news_service import (
    STEAM_RSS_URL,
    MetaSummary,
    NewsItem,
    NewsService,
)
from vetmo.services.supabase_meta import SupabaseMetaService

logger = logging.getLogger("vetmo.news.live")

_CACHE_ITEMS = 5


@dataclass
class _NewsCache:
    items: list[NewsItem]
    fetched_at: float


class LiveNewsService:
    """Steam RSS (TTL 1 час, только память) + мета из Supabase."""

    def __init__(
        self,
        settings: Settings,
        meta: SupabaseMetaService,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._meta = meta
        self._http = http_client or build_http_client(settings.http_timeout)
        self._cache: _NewsCache | None = None

    def get_latest_patch_news(self, limit: int = 5) -> tuple[list[NewsItem], bool]:
        """(items, is_online). is_online оставлен для совместимости UI."""
        now = time.monotonic()
        ttl = max(0.0, float(self._settings.news_ttl_hours) * 3600.0)
        if self._cache is not None and now - self._cache.fetched_at < ttl:
            return list(self._cache.items[: max(0, limit)]), True
        fetched = self._fetch(limit)
        if fetched is not None:
            self._cache = _NewsCache(fetched, now)
            return fetched[: max(0, limit)], True
        if self._cache is not None:
            return list(self._cache.items[: max(0, limit)]), False
        return [], False

    def _fetch(self, limit: int) -> list[NewsItem] | None:
        try:
            response = self._http.get(STEAM_RSS_URL)
        except Exception as exc:  # noqa: BLE001 - сеть не роняет GUI
            logger.warning("Steam RSS недоступен: %s", type(exc).__name__)
            return None
        if response.status_code >= 400:
            logger.warning("Steam RSS: HTTP %s", response.status_code)
            return None
        return NewsService._parse_rss(response.text, limit)

    def get_meta_summary(self, limit: int = 10) -> MetaSummary:
        """Мета-сводка: версия патча + топ по winrate."""
        version, rows = self._meta.get_meta_summary(limit=limit)
        return MetaSummary(
            patch_version=version,
            top=[(row.hero, row.win_rate, row.pick_rate) for row in rows],
        )


__all__ = ["LiveNewsService"]
