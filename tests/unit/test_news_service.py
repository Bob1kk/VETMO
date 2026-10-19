"""Тесты NewsService (T-014): сеть не роняет GUI, offline-состояние (Review Focus #4)."""

import httpx

import vetmo.services.news_service as ns_mod
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.services.news_service import MetaSummary, NewsItem, NewsService


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_news_offline_on_network_error(db) -> None:
    """Сетевая ошибка -> (items, is_online=False), без исключения, items непустые."""
    _, sessionmaker = db

    def broken(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise httpx.ConnectError("no route to host")

    client = httpx.Client(transport=httpx.MockTransport(broken))
    svc = NewsService(sessionmaker, _settings(), http_client=client)
    items, online = svc.get_latest_patch_news()
    assert online is False
    assert len(items) == 1
    assert "Офлайн" in items[0].title


def test_news_offline_on_http_error_status(db) -> None:
    """404/500 — тоже offline fallback, не исключение."""

    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    _, sessionmaker = db
    client = httpx.Client(transport=httpx.MockTransport(fail))
    svc = NewsService(sessionmaker, _settings(), http_client=client)
    items, online = svc.get_latest_patch_news()
    assert online is False and items


def test_news_success_maps_items(db) -> None:
    """Успешный ответ -> маппинг заметок, is_online=True."""

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"version": "7.54", "noun": "Рузвали баланс", "date": "2026-10-01"},
            {"version": "7.53", "noun": "Драйв", "date": "2026-09-01"},
        ])

    _, sessionmaker = db
    client = httpx.Client(transport=httpx.MockTransport(ok))
    svc = NewsService(sessionmaker, _settings(), http_client=client)
    items, online = svc.get_latest_patch_news(limit=1)
    assert online is True
    assert len(items) == 1
    assert items[0] == NewsItem(title="7.54", body="Рузвали баланс", date="2026-10-01")


def test_news_from_db_when_no_network_item(db) -> None:
    """Офлайн, но патчи в БД -> новости из БД (is_online=False, items >1)."""

    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    _, sessionmaker = db
    MetaRepository.ensure_patch(sessionmaker(), "7.53", None, None)
    MetaRepository.ensure_patch(sessionmaker(), "7.54", None, "Баланс-патч")
    client = httpx.Client(transport=httpx.MockTransport(fail))
    svc = NewsService(sessionmaker, _settings(), http_client=client)
    items, online = svc.get_latest_patch_news(limit=1)
    assert online is False
    assert len(items) == 1 and items[0].title == "7.54" and items[0].body == "Баланс-патч"


def test_meta_summary_empty(db) -> None:
    """Пустая БД -> MetaSummary(None, []), без исключений."""
    _, sessionmaker = db
    svc = NewsService(sessionmaker, _settings())
    summary = svc.get_meta_summary()
    assert summary == MetaSummary(patch_version=None, top=[])


def test_meta_summary_from_db(db) -> None:
    """Мета в БД -> patch_version и топ героев."""
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
    assert item.date is None
    summary = MetaSummary(patch_version=None, top=[])
    assert summary.top == []
    assert ns_mod.NewsItem is NewsItem  # публичный символ модуля
