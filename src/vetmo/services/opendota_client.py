"""OpenDota API клиент: кэш >= 24ч, ретраи, rate limit. Контракт T-008."""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.services.validator_service import ValidatorService

logger = logging.getLogger("vetmo.opendota")

_KEY_LAST_SYNC_HEROES = "last_sync_heroes"


@dataclass
class SyncResult:
    """Итог синхронизации: сколько всего/ок/карантина/пропущено."""

    total: int = 0
    ok: int = 0
    quarantined: int = 0
    skipped: int = 0

    def __str__(self) -> str:  # noqa: D105
        return (f"SyncResult(total={self.total}, ok={self.ok}, "
                f"quarantined={self.quarantined}, skipped={self.skipped})")


class OpenDotaClient:
    """HTTP-клиент OpenDota: upsert героев, матчапы; кэш и лимит запросов."""

    MAX_RETRIES: ClassVar[int] = 3

    def __init__(
        self, settings: Any, validator: ValidatorService,
        engine: Engine | None, sessionmaker: sessionmaker[Session],
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._validator = validator
        self._engine = engine
        self._sessionmaker = sessionmaker
        self._http = http_client or httpx.Client(timeout=settings.http_timeout)
        self._min_interval = 60.0 / max(1, int(settings.rate_limit_per_min))
        self._last_request_time = 0.0
        self.retry_delays: tuple[float, ...] = (0.5, 1.0, 2.0)

    # --- HTTP-механика ---
    def _respect_rate_limit(self) -> None:
        """Спит до минимального интервала между запросами."""
        now = time.perf_counter()
        wait = self._min_interval - (now - self._last_request_time)
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.perf_counter()

    def _request(self, path: str) -> Any | None:
        """GET с ретраями (3 попытки, экспоненциальная задержка) на 5xx/сеть."""
        url = f"{str(self._settings.opendota_base_url).rstrip('/')}/{path.lstrip('/')}"
        last_delay_index = len(self.retry_delays) - 1
        for attempt in range(self.MAX_RETRIES):
            self._respect_rate_limit()
            try:
                response = self._http.get(url)
            except httpx.HTTPError as error:
                logger.warning("Запрос %s упал: %s (попытка %s)",
                               path, error, attempt + 1)
                if attempt < last_delay_index:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return None
            if response.status_code >= 500 or response.status_code == 429:
                logger.warning("HTTP %s для %s (попытка %s)",
                               response.status_code, path, attempt + 1)
                if attempt < last_delay_index:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return None
            if response.status_code >= 400:
                logger.warning("HTTP %s для %s — без ретрая", response.status_code, path)
                return None
            try:
                return response.json()
            except ValueError:
                logger.warning("Некорректный JSON от %s", path)
                return None
        return None

    # --- кэш ---
    def _cache_is_fresh(self, settings_repo: SettingsRepository) -> bool:
        """True, если last_sync_heroes моложе cache_ttl_hours."""
        raw = settings_repo.get(_KEY_LAST_SYNC_HEROES)
        if not raw:
            return False
        try:
            last = datetime.fromisoformat(raw)
        except ValueError:
            return False
        now = datetime.now(UTC) if last.tzinfo else datetime.now()
        elapsed_hours = (now - last).total_seconds() / 3600.0
        return elapsed_hours < float(self._settings.cache_ttl_hours)

    # --- синхронизация героев ---
    def sync_heroes(self, limit: int = 120) -> SyncResult:
        """GET heroStats -> upsert героев; кэш TTL -> сеть не трогается."""
        with self._sessionmaker() as session:
            settings_repo = SettingsRepository(session)
            if self._cache_is_fresh(settings_repo):
                count = HeroRepository(session).count()
                return SyncResult(total=count, ok=count)
        data = self._request("heroStats")
        if not isinstance(data, list):
            logger.warning("heroStats недоступен — offline, БД не тронута")
            return SyncResult(skipped=limit)
        data = data[:limit] if limit and limit > 0 else data
        hero_repo = HeroRepository(self._sessionmaker())
        session = hero_repo._session  # noqa: SLF001 — sessionmaker создаёт здесь
        ok = quarantined = 0
        try:
            settings_repo = SettingsRepository(session)
            for record in data:
                if not isinstance(record, dict):
                    continue
                hero = self._map_hero(record)
                if hero is None:
                    quarantined += 1
                    continue
                validation = self._validator.validate_hero({
                    "name": hero.name,
                    "localized_name": hero.localized_name,
                    "icon_url": hero.icon_url,
                })
                if not validation.is_valid:
                    logger.info("Карантин героя %s: %s",
                                hero.id, validation.reason)
                    quarantined += 1
                    continue
                hero_repo.upsert(hero)
                ok += 1
            settings_repo.set(
                _KEY_LAST_SYNC_HEROES, datetime.now(UTC).isoformat())
            session.commit()
        finally:
            session.close()
        return SyncResult(total=len(data), ok=ok, quarantined=quarantined)

    def _map_hero(self, record: dict) -> Hero | None:
        """Сырая запись heroStats -> доменная Hero (или None при плохом id)."""
        try:
            hero_id = int(record.get("id") or 0)
        except (TypeError, ValueError):
            return None
        if hero_id <= 0:
            return None
        icon_raw = record.get("icon") or record.get("img")
        icon_url = self._normalize_icon(icon_raw)
        name = str(record.get("name") or "")
        localized = str(record.get("localized_name") or name)
        roles = record.get("roles")
        return Hero(
            id=hero_id, name=name, localized_name=localized,
            primary_attr=str(record.get("primary_attr") or "all"),
            attack_type=str(record.get("attack_type") or "Melee"),
            roles=[str(r) for r in roles] if isinstance(roles, list) else [],
            icon_url=icon_url,
        )

    @staticmethod
    def _normalize_icon(raw: object) -> str | None:
        """'//cdn/...' -> 'https://cdn/...'; пустое -> None."""
        if not raw:
            return None
        icon = str(raw).strip()
        if icon.startswith("//"):
            return f"https:{icon}"
        return icon

    # --- матчапы (контрпики) ---
    def sync_matchups(
        self, hero_ids: int | list[int] | None = None,
        rivals_per_hero: int = 30,
    ) -> SyncResult:
        """GET heroes/{id}/matchups -> CounterRepository; ошибки — skip."""
        if isinstance(hero_ids, int):
            hero_ids = [hero_ids]
        total = ok = skipped = 0
        with self._sessionmaker() as session:
            ids = (
                hero_ids if hero_ids is not None
                else [h.id for h in HeroRepository(session).get_all()]
            )
            if not ids:
                return SyncResult()
            counter_repo = CounterRepository(session)
            for hero_id in ids:
                data = self._request(f"heroes/{int(hero_id)}/matchups")
                if not isinstance(data, list):
                    logger.warning("matchups %s недоступны", hero_id)
                    skipped += 1
                    continue
                rows = [r for r in data if isinstance(r, dict)]
                rows.sort(key=lambda r: -int(r.get("games_played") or 0))
                for row in rows[:max(1, rivals_per_hero)]:
                    against = self._opponent_id(row)
                    if against is None or against == hero_id:
                        continue
                    games = int(row.get("games_played") or 0)
                    if games <= 0:
                        continue
                    wins = int(row.get("wins") or 0)
                    wr_against = round(
                        max(0.0, min(100.0, wins / games * 100.0)), 2)
                    counter_repo.upsert(int(hero_id), against, wr_against, games)
                    ok += 1
                    total += 1
        return SyncResult(total=total, ok=ok, skipped=skipped)

    @staticmethod
    def _opponent_id(row: dict) -> int | None:
        """Противник из записи matchups: against_hero_id или hero_id."""
        for key in ("against_hero_id", "hero_id"):
            try:
                value = int(row.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None
