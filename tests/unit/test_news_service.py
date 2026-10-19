"""Тесты NewsService v2 (Steam RSS): TTL-кэш, дедуп по url, offline из БД."""

from datetime import UTC, datetime, timedelta

import httpx

import vetmo.services.news_service as ns_mod
from vetmo.data.models_orm import NewsItemORM
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.services.news_service import MetaSummary, NewsItem, NewsService

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Dota 2</title>
  <item>
    <title>Gameplay Patch 7.54</title>
    <link>https://store.steampowered.com/news/patch754</link>
    <pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate>
    <description>&lt;b&gt;Balance changes!&lt;/b&gt; &amp; more &lt;i&gt;hero&lt;/i&gt; styled text here.</description>
  </item>
  <item>
    <title>Battle Pass Update</title>
    <link>https://store.steampowered.com/news/bp</link>
    <pubDate>Thu, 01 Oct 2026 00:00:00 GMT</pubDate>
    <description>Short note</description>
  </item>
</channel></rss>"""


def _settings() -> Settings:
    return Settings(_env_file=None)


def _rss_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_news_rss_parses_and_stores(db) -> None:
    """RSS -> NewsItem (title/body/date/url), HTML вычищен, строки в БД."""
    _, sessionmaker = db

    def ok(request: httpx.Request) -> httpx.Response:
        assert "store.steampowered.com" in str(request.url)
        return httpx.Response(200, text=RSS_XML)

    svc = NewsService(sessionmaker, _settings(), http_client=_rss_client(ok))
    items, online = svc.get_latest_patch_news()
    assert online is True
    assert len(items) == 2
    first = items[0]
    assert first.title == "Gameplay Patch 7.54"
    assert first.url == "https://store.steampowered.com/news/patch754"
    assert first.date == "Sat, 10 Oct 2026 00:00:00 GMT"
    assert "<" not in first.body and "amp;" not in first.body \
        and "lt;" not in first.body
    assert len(first.body) <= 200
    with sessionmaker() as session:
        rows = session.query(NewsItemORM).all()
    assert len(rows) == 2
    assert rows[-1].summary == first.body and rows[-1].url == first.url


def test_news_rss_dedup_by_url_and_ttl(db) -> None:
    """Повторный вызов в TTL: сеть не трогается; дедуп по url — нет дублей."""
    calls = []
    _, sessionmaker = db

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, text=RSS_XML)

    svc = NewsService(sessionmaker, _settings(), http_client=_rss_client(ok))
    svc.get_latest_patch_news()
    svc.get_latest_patch_news()  # свежий TTL: сеть не зовём
    assert len(calls) == 1
    svc2 = NewsService(sessionmaker, _settings(), http_client=_rss_client(ok))
    items, online = svc2.get_latest_patch_news()
    assert len(calls) == 1 and online is True and len(items) == 2
    with sessionmaker() as session:
        assert session.query(NewsItemORM).count() == 2


def test_news_rss_broken_xml_falls_back(db) -> None:
    """Невалидный XML -> offline из БД; DB пуста -> ([], False) без исключений."""
    _, sessionmaker = db

    def broken_xml(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<rss><channel><item><unclosed>")

    svc = NewsService(
        sessionmaker, _settings(), http_client=_rss_client(broken_xml))
    items, online = svc.get_latest_patch_news()
    assert items == [] and online is False


def test_news_offline_returns_saved(db) -> None:
    """Сеть легла после успешного фетча: сохранённые из БД + is_online=False."""
    _, sessionmaker = db

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    rss_svc = NewsService(
        sessionmaker, _settings(), http_client=_rss_client(
            lambda r: httpx.Response(200, text=RSS_XML)))
    rss_svc.get_latest_patch_news()  # кэш БД наполнен
    stale = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    with sessionmaker() as session:
        SettingsRepository(session).set("news_fetched_at", stale)
    offline = NewsService(
        sessionmaker, _settings(), http_client=_rss_client(fail))
    items, online = offline.get_latest_patch_news()
    assert online is False
    assert len(items) == 2
    assert items[0].title == "Gameplay Patch 7.54"


def test_news_empty_db_offline(db) -> None:
    """БД пуста и сеть недоступна -> ([], False), без исключений."""
    _, sessionmaker = db

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    svc = NewsService(sessionmaker, _settings(), http_client=_rss_client(fail))
    assert svc.get_latest_patch_news() == ([], False)


def test_news_stale_cache_refetches(db) -> None:
    """news_fetched_at старше TTL -> сеть ходит заново после 6ч."""
    calls = []
    _, sessionmaker = db

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, text=RSS_XML)

    svc = NewsService(sessionmaker, _settings(), http_client=_rss_client(ok))
    svc.get_latest_patch_news()
    assert len(calls) == 1
    stale = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    with sessionmaker() as session:
        SettingsRepository(session).set("news_fetched_at", stale)
    svc.get_latest_patch_news()
    assert len(calls) == 2


def test_meta_summary_empty(db) -> None:
    """Пустая БД -> MetaSummary(None, []), без исключений."""
    _, sessionmaker = db
    svc = NewsService(sessionmaker, _settings())
    summary = svc.get_meta_summary()
    assert summary == MetaSummary(patch_version=None, top=[])


def test_meta_summary_from_db(db) -> None:
    """Мета в БД -> patch_version и топ героев (UI-контракт: кортежи)."""
    _, sessionmaker = db
    with sessionmaker() as session:
        HeroRepository(session).upsert(
            Hero(id=11, name="hh", localized_name="HH", primary_attr="int",
                 attack_type="Ranged", roles=[], icon_url=None))
    patch_id = MetaRepository.ensure_patch(sessionmaker(), "7.54", None)
    with sessionmaker() as session:
        MetaRepository(session).upsert(patch_id, 11, 55.0, 12.0)
    svc = NewsService(sessionmaker, _settings())
    summary = svc.get_meta_summary()
    assert summary.patch_version == "7.54"
    assert summary.top and summary.top[0][0].id == 11
    assert summary.top[0][1] == 55.0


def test_news_dataclasses() -> None:
    """NewsItem/MetaSummary — чистые dataclasses."""
    item = NewsItem(title="t", body="b")
    assert item.date is None and item.url is None
    summary = MetaSummary(patch_version=None, top=[])
    assert summary.top == []
    assert ns_mod.NewsItem is NewsItem  # публичный символ модуля
