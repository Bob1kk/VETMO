"""Сервис новостей/меты: сеть не роняет GUI, offline-состояние. Контракт T-014."""

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.models_orm import PatchORM
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.infra.proxy import system_proxy_url


@dataclass
class NewsItem:
    """Одна новостная заметка о патче."""

    title: str
    body: str
    date: str | None = None


@dataclass
class MetaSummary:
    """Итог мета-обзора: версия патча и топ героев по win_rate."""

    patch_version: str | None
    top: list[tuple[Hero, float, float]]


class NewsService:
    """Новости патчей и мета-сводка; никогда не бросает исключение наружу."""

    def __init__(
        self, sessionmaker: sessionmaker[Session], settings: Settings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        proxy_url = system_proxy_url()
        proxy = httpx.Proxy(proxy_url) if proxy_url else None
        self._http = http_client or httpx.Client(timeout=settings.http_timeout, proxy=proxy)

    def get_latest_patch_news(self, limit: int = 5) -> tuple[list[NewsItem], bool]:
        """(items, is_online): сеть не удалась -> offline fallback из БД."""
        url = f"{self._settings.opendota_base_url}patchNotes"
        try:
            response = self._http.get(url)
        except Exception:  # noqa: BLE001 — network must not crash GUI
            return self._offline_news(limit), False
        if response.status_code >= 400:
            return self._offline_news(limit), False
        try:
            data = response.json()
        except ValueError:
            return self._offline_news(limit), False
        if not isinstance(data, list):
            return self._offline_news(limit), False
        items = [
            NewsItem(
                title=str(row.get("version") or ""),
                body=str(row.get("noun") or row.get("title") or ""),
                date=row.get("date") if isinstance(row.get("date"), str) else None,
            )
            for row in data[:limit] if isinstance(row, dict)
        ]
        return items, True

    def _offline_news(self, limit: int) -> list[NewsItem]:
        """Fallback: патчи из БД; если пусто — заглушка офлайн-режима."""
        with self._sessionmaker() as session:
            rows = (
                session.query(PatchORM)
                .order_by(PatchORM.id.desc())
                .limit(limit)
                .all()
            )
        items = [
            NewsItem(title=r.version, body=r.note or "", date=None)
            for r in rows
        ]
        if not items:
            items = [NewsItem(
                title="Офлайн-режим",
                body="Нет данных о патчах. Запустите синхронизацию при наличии сети.",
            )]
        return items

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
        return MetaSummary(patch_version=version, top=top)
