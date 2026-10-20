"""Сервис новостей/меты: Steam RSS, TTL 6ч, сеть не роняет GUI. R2 (задача 5)."""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.models_orm import NewsItemORM, PatchORM
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.infra.http_client import build_http_client

logger = logging.getLogger("vetmo.news")

# Steam RSS: новости Dota 2 (app 570). Формат — обычный XML RSS 2.0.
STEAM_RSS_URL = "https://store.steampowered.com/feeds/news/app/570/?cc=us&l=english"
_KEY_NEWS_FETCHED = "news_fetched_at"
_SUMMARY_LIMIT = 200
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsItem:
    """Одна новостная заметка о патче (body=summary, date=публикация)."""

    title: str
    body: str
    date: str | None = None
    url: str | None = None


@dataclass
class MetaSummary:
    """Итог мета-обзора: версия патча и топ героев по win_rate."""

    patch_version: str | None
    top: list[tuple[Hero, float, float]]


class NewsService:
    """Новости патчей (Steam RSS) и мета-сводка; никогда не роняет GUI."""

    def __init__(
        self, sessionmaker: sessionmaker[Session], settings: Settings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._http = http_client or build_http_client(settings.http_timeout)

    def get_latest_patch_news(self, limit: int = 5) -> tuple[list[NewsItem], bool]:
        """(items, is_online): Steam RSS, TTL 6ч; сбой сети -> из БД + False.

        Свежий кэш (news_fetched_at моложе news_ttl_hours) -> данные из БД,
        is_online=True. Если и сеть упала, и в БД пусто -> ([], False).
        """
        with self._sessionmaker() as session:
            settings_repo = SettingsRepository(session)
            if self._cache_is_fresh(settings_repo):
                cached = self._news_from_db(limit)
                if cached:
                    return cached, True
            fetched = self._fetch_rss(limit)
            if fetched is not None:  # успех: сохранить + зафиксировать TTL
                self._store_news(session, fetched)
                settings_repo.set(
                    _KEY_NEWS_FETCHED, datetime.now(UTC).isoformat())
                return fetched[:max(0, limit)], True
            cached = self._news_from_db(limit)
            return cached, False  # пустая БД + нет сети -> ([], False)

    def _cache_is_fresh(self, settings_repo: SettingsRepository) -> bool:
        """True, если news_fetched_at моложе news_ttl_hours."""
        raw = settings_repo.get(_KEY_NEWS_FETCHED)
        if not raw:
            return False
        try:
            last = datetime.fromisoformat(raw)
        except ValueError:
            return False
        now = datetime.now(UTC) if last.tzinfo else datetime.now()
        elapsed_hours = (now - last).total_seconds() / 3600.0
        return elapsed_hours < float(self._settings.news_ttl_hours)

    def _fetch_rss(self, limit: int) -> list[NewsItem] | None:
        """Грузит Steam RSS; возвращает NewsItem или None при любой ошибке."""
        try:
            response = self._http.get(STEAM_RSS_URL)
        except Exception as error:  # noqa: BLE001 — сеть не должна ронять GUI
            logger.warning("Steam RSS недоступен: %s", error)
            return None
        if response.status_code >= 400:
            logger.warning("Steam RSS: HTTP %s", response.status_code)
            return None
        return self._parse_rss(response.text, limit)

    @staticmethod
    def _parse_rss(xml_text: str, limit: int) -> list[NewsItem] | None:
        """XML RSS -> NewsItem (description чистится от HTML, ~200 симв)."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as error:
            logger.warning("Steam RSS: невалидный XML: %s", error)
            return None
        items: list[NewsItem] = []
        for node in root.iter("item"):
            title = (node.findtext("title") or "").strip()
            url = (node.findtext("link") or "").strip()
            published = (node.findtext("pubDate") or "").strip() or None
            summary = _strip_html(node.findtext("description") or "")
            if not url:
                continue
            items.append(NewsItem(
                title=title, body=summary, date=published, url=url))
            if len(items) >= max(0, limit) * 4:  # запас на дедуп по url
                break
        unique: list[NewsItem] = []
        seen: set[str] = set()
        for item in items:
            if item.url and item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        return unique[:max(0, limit)]

    @staticmethod
    def _store_news(session: Session, items: list[NewsItem]) -> None:
        """Сохраняет новости в БД; dedup-ключ = url (ON CONFLICT).

        Пишем в обратном порядке: последние в ленте получают больший id —
        тогда чтение ORDER BY id DESC возвращает их первыми.
        """
        for item in reversed(items):
            if not item.url:
                continue
            stmt = sqlite_insert(NewsItemORM).values(
                title=item.title, url=item.url,
                published=item.date, summary=item.body,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "title": stmt.excluded.title,
                    "published": stmt.excluded.published,
                    "summary": stmt.excluded.summary,
                },
            )
            session.execute(stmt)
        session.commit()

    def _news_from_db(self, limit: int) -> list[NewsItem]:
        """Новости из БД (свежие сверху) в доменном виде."""
        with self._sessionmaker() as session:
            rows = (
                session.query(NewsItemORM)
                .order_by(NewsItemORM.id.desc())
                .limit(max(0, limit))
                .all()
            )
        return [
            NewsItem(
                title=r.title, body=r.summary or "",
                date=r.published, url=r.url)
            for r in rows
        ]

    def get_meta_summary(self, limit: int = 10) -> MetaSummary:
        """Мета из БД: версия последнего патча и топ героев; пусто -> None/[]"""
        with self._sessionmaker() as session:
            patch = (
                session.query(PatchORM)
                .order_by(PatchORM.id.desc())
                .first()
            )
            top = MetaRepository(session).get_top_meta(limit)
        version = patch.version if patch else None
        # UI-контракт v1 оставлен: [(Hero, win_rate, pick_rate), ...]
        return MetaSummary(
            patch_version=version,
            top=[(row.hero, row.win_rate, row.pick_rate) for row in top],
        )


def _strip_html(raw: str) -> str:
    """Убирает HTML-теги, схлопывает пробелы, режет до ~200 символов."""
    text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", raw)).strip()
    return text[:_SUMMARY_LIMIT]
