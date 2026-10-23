"""OpenDota API клиент: кэш >= 24ч, ретраи, rate limit. Контракт T-008 + R2."""

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.infra.http_client import build_http_client
from vetmo.services.validator_service import ValidatorService

logger = logging.getLogger("vetmo.opendota")

_KEY_LAST_SYNC_HEROES = "last_sync_heroes"
_KEY_MATCHUPS_SYNCED = "matchups_synced_hero_ids"
_KEY_MATCHUPS_SYNCED_AT = "matchups_synced_at"
PATCH_PUBLIC_LADDER = "public-ladder"  # fallback, если /constants/patch недоступен
_PATCH_NAME_RE = re.compile(r"^\d+\.\d+[a-z]?$")
RANK_TIERS: tuple[int, ...] = tuple(range(1, 9))  # 1=Herald..8=Immortal
ICON_TIMEOUT = 10.0
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def _is_valid_png(path: Path) -> bool:
    """Проверяет сигнатуру PNG: 0-байтный/битый кэш не считается валидным."""
    try:
        with path.open("rb") as handle:
            return handle.read(len(_PNG_SIGNATURE)) == _PNG_SIGNATURE
    except OSError:
        return False


def _progress_is_fresh(raw_at: str | None, ttl_hours: float) -> bool:
    """True, если незавершённый прогресс синхронизации ещё актуален."""
    if not raw_at:
        return False
    try:
        started = datetime.fromisoformat(raw_at)
    except ValueError:
        return False
    now = datetime.now(UTC) if started.tzinfo else datetime.now()
    elapsed = (now - started).total_seconds() / 3600.0
    return 0.0 <= elapsed < max(0.0, float(ttl_hours))


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
        self._http = http_client or build_http_client(settings.http_timeout)
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

    def latest_patch(self) -> tuple[str, datetime | None]:
        """Последний патч Dota: (версия, дата релиза | None).

        Берём максимальный ``id`` из ``/constants/patch``; дата приходит
        ISO-строкой (``2026-03-24T00:50:59.580Z``) и сохраняется в БД как
        naive UTC. heroStats — скользящий срез публичных матчей, поэтому
        патч остаётся меткой источника, а не гарантией «только этот патч».
        Если справочник недоступен/ответ не похож на патчи — безопасный
        fallback ``public-ladder`` без даты.
        """
        data = self._request("constants/patch")
        candidates: list[tuple[int, str, datetime | None]] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                raw_id = item.get("id")
                if raw_id is None:
                    continue
                try:
                    patch_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if _PATCH_NAME_RE.fullmatch(name):
                    candidates.append((
                        patch_id, name, self._patch_date(item.get("date"))))
        if not candidates:
            logger.info("Справочник патчей недоступен — метка public-ladder")
            return PATCH_PUBLIC_LADDER, None
        _, name, released = max(candidates, key=lambda item: item[0])
        return name, released

    def latest_patch_version(self) -> str:
        """Только версия последнего патча (совместимый helper)."""
        return self.latest_patch()[0]

    def fetch_hero_stats(self) -> list[dict[str, Any]] | None:
        """Сырой список ``heroStats`` (последние 7 дней) без кэш-логики."""
        data = self._request("heroStats")
        return data if isinstance(data, list) else None

    @staticmethod
    def _patch_date(raw: object) -> datetime | None:
        """ISO-дата OpenDota -> naive UTC; битую строку игнорируем."""
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed

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
    def sync_heroes(
        self, limit: int = 0, data: list[dict[str, Any]] | None = None
    ) -> SyncResult:
        """GET heroStats -> upsert героев + мета v2; кэш TTL -> сеть не трогается.

        ``data`` позволяет передать уже загруженный ``heroStats`` (чтобы не
        делать второй запрос при записи меты в Supabase).

        limit: 0 — синхронизировать всех героев (каталог OpenDota растёт,
        фиксированные 120 оставляли новых героев без данных и искажали
        pick_rate, посчитанный по урезанной выборке).

        Мета: (1) rank_tier=None — общий pub: win=pub_win/pub_pick*100,
        pick — относительная доля pub_pick *1000 (кап 100); (2) для каждого
        тира t=1..8 с {t}_pick>0 — row rank_tier=t, win={t}_win/{t}_pick*100,
        pick — доля в тире (1000*{t}_pick/Σ{t}_pick, кап 100). ban_rate —
        доля про-банов pro_ban/(pro_pick+pro_ban)*100 (кап 100); пишется
        только в общий срез rank_tier=None, потому что OpenDota не отдаёт
        pro-баны в разбивке по рангам.
        """
        with self._sessionmaker() as session:
            settings_repo = SettingsRepository(session)
            if self._cache_is_fresh(settings_repo):
                count = HeroRepository(session).count()
                return SyncResult(total=count, ok=count)
        if data is None:
            data = self._request("heroStats")
        if not isinstance(data, list):
            logger.warning("heroStats недоступен — offline, БД не тронута")
            return SyncResult(skipped=max(1, limit))
        patch_version, patch_date = self.latest_patch()
        data = data[:limit] if limit and limit > 0 else data
        records = [r for r in data if isinstance(r, dict)]

        # Winrate = win/pick*100; pick_rate — относительная доля пиков ×1000
        # (сумма по героям ≈ 1000 ÷ 10 слотов матча), кап 100.
        total_pub_pick = sum(float(r.get("pub_pick") or 0) for r in records)
        tier_totals = {
            tier: sum(float(r.get(f"{tier}_pick") or 0) for r in records)
            for tier in RANK_TIERS
        }
        totals: dict[int, float] = {0: total_pub_pick, **tier_totals}

        ok = quarantined = 0
        with self._sessionmaker() as session:
            meta_repo = MetaRepository(session)
            hero_repo = HeroRepository(session)
            settings_repo = SettingsRepository(session)
            patch: int | None = None
            if total_pub_pick > 0:
                patch = MetaRepository.ensure_patch(
                    session, patch_version, patch_date,
                    "OpenDota heroStats: rolling public matches; "
                    "pro-баны — общий pro-срез, не по рангам",
                    commit=False,
                )
            for record in records:
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
                hero_repo.upsert(hero, commit=False)
                if patch is not None:
                    bad = self._write_meta_rows(
                        record, hero.id, patch, meta_repo, totals)
                    quarantined += bad
                ok += 1
            settings_repo.set(
                _KEY_LAST_SYNC_HEROES, datetime.now(UTC).isoformat(),
                commit=False,
            )
            # Один commit на весь срез: обрыв/исключение не оставит БД
            # наполовину обновлённой.
            session.commit()
        return SyncResult(total=len(data), ok=ok, quarantined=quarantined)

    def _write_meta_rows(
        self, record: dict, hero_id: int, patch_id: int,
        meta_repo: MetaRepository, totals: dict[int, float],
    ) -> int:
        """Пишет мета-строки героя (pub + тиры); возвращает число карантинов."""
        pro_pick = float(record.get("pro_pick") or 0)
        pro_ban = float(record.get("pro_ban") or 0)
        pro_denom = pro_pick + pro_ban
        ban_rate = min(100.0, 100.0 * pro_ban / pro_denom) if pro_denom > 0 else 0.0

        pub_pick = float(record.get("pub_pick") or 0)
        pub_win = float(record.get("pub_win") or 0)
        rows: list[tuple[int | None, float, float]] = []
        if pub_pick > 0 and totals.get(0):
            rows.append((
                None, 100.0 * pub_win / pub_pick,
                1000.0 * pub_pick / totals[0],
            ))
        for tier in RANK_TIERS:
            tier_pick = float(record.get(f"{tier}_pick") or 0)
            tier_total = totals.get(tier) or 0.0
            if tier_pick <= 0 or tier_total <= 0:
                continue
            rows.append((
                tier,
                100.0 * float(record.get(f"{tier}_win") or 0) / tier_pick,
                1000.0 * tier_pick / tier_total,
            ))

        quarantined = 0
        for rank_tier, wr, pick in rows:
            win_rate = round(max(0.0, min(100.0, wr)), 2)
            pick_rate = round(max(0.0, min(100.0, pick)), 2)
            meta_check = self._validator.validate_meta(
                {"win_rate": win_rate, "pick_rate": pick_rate})
            if meta_check.quarantined:
                logger.warning(
                    "Мета %s (герой %s, тир %s) в карантине: %s",
                    win_rate, hero_id, rank_tier, meta_check.reason,
                )
                quarantined += 1
                continue
            meta_repo.upsert(
                patch_id, hero_id, win_rate, pick_rate,
                rank_tier=rank_tier,
                # Pro-баны не имеют разбивки по рангам: не переносим их
                # на rank_tier-строки, иначе выдаём общий pro-срез за ранг.
                ban_rate=ban_rate if rank_tier is None else 0.0,
                commit=False,
            )
        return quarantined

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
        """'//cdn/...' -> 'https://cdn/...'; '/apps/...' -> cdn.dota2.com; пустое -> None."""
        if not raw:
            return None
        icon = str(raw).strip()
        if not icon:
            return None
        if icon.startswith("//"):
            return f"https:{icon}"
        if icon.startswith("/"):
            # Относительный путь OpenDota: '/apps/dota2/...' -> steamstatic
            # CDN (cdn.dota2.com сейчас отдаёт невалидный сертификат).
            return f"https://cdn.cloudflare.steamstatic.com{icon.split('?')[0]}"
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
        for hero_id in ids:
            count = self._sync_matchups_for_hero(
                hero_id, rivals_per_hero=rivals_per_hero, min_games=0)
            if count is None:
                skipped += 1
                continue
            ok += count
            total += count
        return SyncResult(total=total, ok=ok, skipped=skipped)

    def sync_matchups_all(
        self, resume: bool = True, min_games: int = 100,
    ) -> dict[str, Any]:
        """Контрпики ВСЕХ героев БД (все пары с games >= min_games).

        Resume: ключ settings `matchups_synced_hero_ids` (JSON-список) —
        прогресс обновляется ПОСЛЕ каждого успешного героя, обрыв сети
        продолжается с того места. Возвращает dict:
        {"total": строк, "synced": героев ок, "skipped": героев пропущено,
        "last_hero_id": id последнего успешного или None}.
        """
        with self._sessionmaker() as session:
            hero_ids = [h.id for h in HeroRepository(session).get_all()]
            settings_repo = SettingsRepository(session)
            raw = settings_repo.get(_KEY_MATCHUPS_SYNCED)
            raw_at = settings_repo.get(_KEY_MATCHUPS_SYNCED_AT)
        if not hero_ids:
            return {"total": 0, "synced": 0, "skipped": 0, "last_hero_id": None}
        done: set[int] = set()
        if resume and raw and _progress_is_fresh(
            raw_at, self._settings.cache_ttl_hours,
        ):
            try:
                done = {int(x) for x in json.loads(raw)}
            except (TypeError, ValueError):
                logger.warning("Плохой ключ %s — начинаем заново",
                               _KEY_MATCHUPS_SYNCED)
                done = set()
        elif raw:
            logger.info("Прогресс matchups устарел — обновляем всех героев")
        todo = [i for i in hero_ids if i not in done]
        rows = synced = skipped = 0
        last: int | None = None
        for hero_id in todo:
            count = self._sync_matchups_for_hero(
                hero_id, rivals_per_hero=0, min_games=min_games)
            if count is None:
                logger.warning("matchups %s пропущены (resume продолжит)",
                               hero_id)
                skipped += 1
                continue
            synced += 1
            rows += count
            last = hero_id
            done.add(hero_id)
            with self._sessionmaker() as session:
                repo = SettingsRepository(session)
                repo.set(_KEY_MATCHUPS_SYNCED, json.dumps(sorted(done)))
                repo.set(
                    _KEY_MATCHUPS_SYNCED_AT, datetime.now(UTC).isoformat())
        return {"total": rows, "synced": synced, "skipped": skipped,
                "last_hero_id": last}

    def _sync_matchups_for_hero(
        self,
        hero_id: int, rivals_per_hero: int = 0, min_games: int = 0,
    ) -> int | None:
        """Матчапы одного героя; None при сетевом сбои, число записей при ок.

        rivals_per_hero: 0 — без ограничения (все соперники); иначе top-N
        по games_played. min_games — минимальная выборка пары (R2: 100).
        """
        data = self._request(f"heroes/{int(hero_id)}/matchups")
        if not isinstance(data, list):
            logger.warning("matchups %s недоступны", hero_id)
            return None
        rows = [r for r in data if isinstance(r, dict)]
        rows.sort(key=lambda r: -int(r.get("games_played") or 0))
        count = 0
        with self._sessionmaker() as session:
            counter_repo = CounterRepository(session)
            for row in rows:
                games = int(row.get("games_played") or 0)
                if games <= 0 or games < min_games:
                    continue
                if rivals_per_hero > 0 and count >= rivals_per_hero:
                    break
                against = self._opponent_id(row)
                if against is None or against == hero_id:
                    continue
                wins = int(row.get("wins") or 0)
                wr_against = round(
                    max(0.0, min(100.0, wins / games * 100.0)), 2)
                counter_repo.upsert(int(hero_id), against, wr_against, games)
                count += 1
        return count

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

    # --- кэш иконок (R2) ---
    def sync_icon_cache(
        self, icons_dir: Path | str = Path("assets/cache/icons"),
        http_client: httpx.Client | None = None,
    ) -> dict[str, int]:
        """Скачивает icon_url героев в {icons_dir}/{hero_id}.png.

        Кэш: существующий файл переиспользуется только если это настоящий
        PNG (сигнатура + размер). Битая/пустая картинка перекачивается.
        Сбои сети не крашат (лог + failed). Возвращает
        {"downloaded": n, "cached": m, "failed": k}.
        """
        icons = Path(icons_dir)
        with self._sessionmaker() as session:
            heroes = HeroRepository(session).get_all()
        result = {"downloaded": 0, "cached": 0, "failed": 0}
        if not heroes:
            return result
        icons.mkdir(parents=True, exist_ok=True)
        http = None
        try:
            http = http_client
            if http is None:
                http = build_http_client(ICON_TIMEOUT)
            for hero in heroes:
                target = icons / f"{hero.id}.png"
                if _is_valid_png(target):
                    result["cached"] += 1
                    continue
                if not hero.icon_url:
                    logger.warning("Иконка %s: url пуст", hero.id)
                    result["failed"] += 1
                    continue
                try:
                    response = http.get(hero.icon_url)
                    if response.status_code >= 400:
                        logger.warning(
                            "Иконка %s: HTTP %s", hero.id, response.status_code)
                        result["failed"] += 1
                        continue
                    content = response.content
                    if not content.startswith(_PNG_SIGNATURE):
                        logger.warning(
                            "Иконка %s: ответ не PNG (%s байт)",
                            hero.id, len(content))
                        result["failed"] += 1
                        continue
                    # Атомарная замена: UI не увидит недописанный файл.
                    temporary = target.with_name(f".{hero.id}.png.tmp")
                    temporary.write_bytes(content)
                    temporary.replace(target)
                    result["downloaded"] += 1
                except Exception as error:  # noqa: BLE001 — иконки не критичны
                    logger.warning("Иконка %s: сеть упала: %s", hero.id, error)
                    result["failed"] += 1
        finally:
            if http is not None and http_client is None:
                http.close()
        return result
