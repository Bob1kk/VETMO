"""Sync reference-данных -> Supabase (service_role), отдельно от приложения.

Разделение ответственности (beta2):
  * OpenDota (без токена) -> héros + патчи + главная мета
    (win_rate, pick_rate, ban_rate) — функция :func:`sync_opendota_meta`.
  * STRATZ (токен только в secrets.env) -> контрпики/синергия
    (vetmo_hero_matchups) и опционально баны (vetmo_ban_stats)
    — функция :func:`sync_stratz_matchups`.

Запуск:
    .\\.venv\\Scripts\\python.exe tools\\sync_opendota.py --dry-run
    .\\.venv\\Scripts\\python.exe tools\\sync_opendota.py
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --no-matchups

Приложение никогда не получает service_role: запись выполняет только
этот sync-скрипт. Пользовательское приложение читает уже агрегированные
строки через anon-ключ Supabase.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from vetmo.data.db import create_db
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.supabase_heroes import load_seed_heroes
from vetmo.domain.rank_brackets import ALL_BRACKET, BASIC_BRACKETS
from vetmo.infra.config import Settings
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.infra.sync_settings import SyncSettings
from vetmo.services.opendota_client import OpenDotaClient
from vetmo.services.stratz_aggregate import (
    _day_index,
    ban_rates_by_rank,
    ban_stats_rows,
    hero_rows,
    matchup_bracket_rows,
    patch_rows,
)
from vetmo.services.stratz_client import StratzClient, StratzError
from vetmo.services.validator_service import ValidatorService

logger = logging.getLogger("vetmo.sync")


@dataclass
class SyncStats:
    """Счётчики sync-прогона (для статуса и лога)."""

    patch_version: str | None = None
    patch_id: int | None = None
    rows_meta: int = 0
    rows_matchups: int = 0
    slices: int = 0
    errors: list[str] = field(default_factory=list)
    period: str | None = None
    source: str = "combined"


# ======================================================================
# OpenDota: главная мета (герои, патчи, win/pick/ban)
# ======================================================================

def _service_gateway(sync: SyncSettings) -> SupabaseGateway:
    settings = Settings(
        supabase_url=sync.supabase_url,
        supabase_anon_key=sync.service_key,
    )
    return SupabaseGateway(settings)


def _upsert(gateway: SupabaseGateway, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
    if rows:
        gateway.upsert(table, rows, on_conflict=conflict)


def sync_opendota_meta(
    *,
    dry_run: bool = False,
    trigger: str | None = None,
    request_id: str | None = None,
    progress=print,
) -> SyncStats:
    """Синхронизирует основную мету из OpenDota heroStats.

    Этап 1 — OpenDota API -> локальная SQLite (vetmo.db): герои +
    meta_snapshots (через OpenDotaClient.sync_heroes).
    Этап 2 — локальная SQLite -> Supabase: vetmo_heroes, vetmo_patches,
    vetmo_meta (денормализованно: герой + снэпшот).

    Не требует токена API. service_role используется только для записи в
    Supabase; приложение его не получает.
    """
    sync = SyncSettings.load()
    stats = SyncStats(source="opendota")
    stats.patch_version = None
    stats.patch_id = None

    engine, sessionmaker = create_db("sqlite:///vetmo.db")
    client = OpenDotaClient(
        settings=sync,
        validator=ValidatorService(),
        engine=engine,
        sessionmaker=sessionmaker,
    )

    gateway = None if dry_run else _service_gateway(sync)

    try:
        # --- Этап 1: OpenDota API -> локальная SQLite ---
        patch_version, patch_date = client.latest_patch()
        stats.patch_version = patch_version
        progress(f"OpenDota патч: {patch_version}")

        sync_result = client.sync_heroes(limit=0)
        stats.rows_meta = sync_result.ok
        progress(
            f"Герои: ok={sync_result.ok}, "
            f"quarantined={sync_result.quarantined}, "
            f"total={sync_result.total}"
        )

        # --- Этап 2: локальная SQLite -> Supabase ---
        if gateway is not None:
            with sessionmaker() as session:
                heroes = HeroRepository(session).get_all()
                snapshots = MetaRepository(session).get_top_meta(limit=10000)
                latest_patch_id = MetaRepository(session).latest_patch_id()

            stats.patch_id = latest_patch_id

            # Герои -> vetmo_heroes
            if heroes:
                _upsert(
                    gateway, "vetmo_heroes",
                    hero_rows(heroes), "id",
                )
                progress(f"  vetmo_heroes: {len(heroes)} строк")

            # Патч -> vetmo_patches
            if patch_version:
                _upsert(
                    gateway, "vetmo_patches",
                    [{"id": 0, "game_version_id": 0, "version": patch_version,
                      "release_date": None, "is_current": True, "source": "opendota"}],
                    "id",
                )
                progress(f"  vetmo_patches: {patch_version}")

            # Мета -> vetmo_meta (денормализованно)
            meta_rows: list[dict[str, Any]] = []
            for row in snapshots:
                hero = row.hero
                meta_rows.append({
                    "hero_id": row.hero_id,
                    "name": hero.localized_name or row.name or f"hero_{row.hero_id}",
                    "internal_name": row.name or hero.name or f"hero_{row.hero_id}",
                    "icon_url": hero.icon_url if hero else None,
                    "primary_attr": hero.primary_attr if hero else "",
                    "attack_type": hero.attack_type if hero else "",
                    "win_rate": row.win_rate,
                    "pick_rate": row.pick_rate,
                    "ban_rate": row.ban_rate,
                    "delta_win": row.delta_win,
                    "delta_pick": row.delta_pick,
                    "delta_ban": row.delta_ban,
                    "patch_version": row.patch_version or patch_version,
                    "match_count": row.match_count,
                    "ban_scope": None,
                    "sample_reliable": row.sample_reliable,
                    "source": "opendota",
                    "positions": row.positions,
                    "rank_tier": None,
                })
            if meta_rows:
                _upsert(
                    gateway, "vetmo_meta",
                    meta_rows,
                    "patch_id,hero_id,rank_tier",
                )
                progress(f"  vetmo_meta: {len(meta_rows)} строк")

        # quarantine-флаг отражается в stats.errors при необходимости

    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"{type(exc).__name__}: {exc}")
        progress(f"ОШИБКА OpenDota: {type(exc).__name__}: {exc}")
        raise
    return stats


# ======================================================================
# STRATZ: только матчапы (контрпики/синергия) и баны
# ======================================================================

def sync_stratz_matchups(
    *,
    dry_run: bool = False,
    include_ban_day: bool = True,
    ranks: range = range(0, 9),
    positions: range = range(0, 6),
    trigger: str | None = None,
    request_id: str | None = None,
    progress=print,
    should_stop: Callable[[], bool] | None = None,
) -> SyncStats:
    """Синхронизирует матчапы и баны из STRATZ GraphQL.

    Не трогает главную мету (win/pick/ban) — она теперь из OpenDota.
    Требует STRATZ токена (только в %APPDATA%/VETMO/secrets.env).
    """
    sync = SyncSettings.load()
    client = StratzClient(sync.stratz_token)
    stats = SyncStats(source="stratz")
    gateway = None if dry_run else _service_gateway(sync)
    include_trigger_source = (
        gateway is not None and _supports_column(gateway, "trigger_source")
    )
    include_request_id = gateway is not None and _supports_column(gateway, "request_id")
    run_id: int | None = None
    cancelled = False

    def stop_requested() -> bool:
        nonlocal cancelled
        if not cancelled and should_stop is not None and should_stop():
            cancelled = True
            progress("  отмена: завершаю текущий срез")
        return cancelled

    try:
        versions = client.game_versions()
        if not versions:
            raise StratzError("constants.gameVersions пуст")
        current_id = max(int(v["id"]) for v in versions)
        current_name = next(
            (str(v["name"]) for v in versions if int(v["id"]) == current_id), None,
        )
        stats.patch_id = current_id
        stats.patch_version = current_name
        progress(f"STRATZ патч: {current_name} (id {current_id})")

        if gateway is not None:
            _upsert(gateway, "vetmo_heroes", hero_rows(load_seed_heroes()), "id")
            _upsert(
                gateway, "vetmo_patches",
                patch_rows(versions, current_id=current_id, limit=40), "id",
            )
            run_payload: dict[str, Any] = {
                "status": "running", "source": "stratz",
                "patch_version": current_name,
                **_optional_field(
                    include_trigger_source, "trigger_source", trigger,
                ),
                **_optional_field(include_request_id, "request_id", request_id),
                "details": _trace_details(trigger, request_id),
            }
            run = gateway.insert("vetmo_sync_runs", [run_payload])
            run_id = int(run[0]["id"]) if run else None

        # --- banDay: пер-геройные баны (опционально) ---
        ban_rates: dict[int, dict[int, float]] = {}
        ban_deltas: dict[int, dict[int, float]] = {}
        if include_ban_day and not stop_requested():
            try:
                ban_raw = client.ban_day(days=30)
                ban_days = [
                    day for day in (_day_index(row.get("day")) for row in ban_raw)
                    if day is not None
                ]
                end_day = max(ban_days) if ban_days else None
                ban_rates, ban_deltas = ban_rates_by_rank(
                    ban_raw, end_day=end_day,
                )
                diag = ban_stats_rows(
                    ban_raw, patch_id=current_id, end_day=end_day,
                )
                if gateway is not None and diag:
                    try:
                        _upsert(
                            gateway, "vetmo_ban_stats", diag,
                            "snapshot_date,patch_id,rank_tier,bracket",
                        )
                    except Exception as exc:  # noqa: BLE001 - диагностика
                        stats.errors.append(
                            f"ban_stats: {type(exc).__name__}: {exc}")
                progress(
                    f"  баны: ранги {sorted(ban_rates)}, окно до дня {end_day}"
                )
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(
                    f"ban_day: {type(exc).__name__}: {exc}")
                progress(f"  ОШИБКА ban_day: {type(exc).__name__}: {exc}")

        # --- matchUp: матчапы за текущую неделю ---
        hero_ids = [hero.id for hero in load_seed_heroes()]
        specs: list[tuple[str, str | None]] = [(ALL_BRACKET, None)]
        specs.extend((bracket, bracket) for bracket in BASIC_BRACKETS)
        fetched: list[dict[str, Any]] = []
        failed_brackets: list[str] = []
        slice_count = 0

        for rank_bracket, bracket in specs:
            if stop_requested():
                break
            try:
                groups = client.matchup_groups(
                    hero_ids, take=300, bracket=bracket,
                )
                bracket_rows: list[dict[str, Any]] = []
                for hero_id in hero_ids:
                    bracket_rows.extend(matchup_bracket_rows(
                        hero_id,
                        groups.get(hero_id, {}),
                        patch_id=current_id,
                        rank_bracket=rank_bracket,
                        include_full_vs=(rank_bracket == ALL_BRACKET),
                    ))
                fetched.extend(bracket_rows)
                slice_count += 1
                progress(
                    f"  матчапы {rank_bracket}: {len(bracket_rows)} строк"
                )
            except Exception as exc:  # noqa: BLE001 - один срез не рушит sync
                failed_brackets.append(rank_bracket)
                message = (
                    f"matchup {rank_bracket}: {type(exc).__name__}: {exc}"
                )
                stats.errors.append(message)
                progress(f"  ОШИБКА {message}")
            time.sleep(0.1)

        stats.rows_matchups = len(fetched)
        stats.slices = slice_count

        if gateway is not None and cancelled:
            stats.errors.append("matchups: запись пропущена из-за отмены")
        elif gateway is not None and fetched and not failed_brackets:
            try:
                gateway.delete(
                    "vetmo_hero_matchups", {"patch_id": int(current_id)},
                )
                _upsert(
                    gateway, "vetmo_hero_matchups", fetched,
                    "patch_id,hero_id,kind,rank_bracket,vs_hero_id",
                )
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(
                    f"matchups write: {type(exc).__name__}: {exc}")
        elif gateway is not None and failed_brackets:
            stats.errors.append(
                "matchups: запись пропущена, чтобы не потерять старые "
                f"данные (сбои: {', '.join(failed_brackets)})")

        if cancelled:
            stats.errors.append("sync отменён пользователем")

        if gateway is not None and run_id is not None:
            status = "ok" if not stats.errors else "partial"
            gateway.update(
                "vetmo_sync_runs",
                {
                    "status": status,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "rows_meta": stats.rows_meta,
                    "rows_matchups": stats.rows_matchups,
                    **_optional_field(
                        include_trigger_source, "trigger_source", trigger,
                    ),
                    **_optional_field(
                        include_request_id, "request_id", request_id,
                    ),
                    "details": {
                        "slices": stats.slices,
                        "period_end": stats.period,
                        "source": "stratz-matchups-ban",
                        "cancelled": cancelled,
                        "errors": stats.errors[:20],
                        **_trace_details(trigger, request_id),
                    },
                    "error": "; ".join(stats.errors[:5]) or None,
                },
                {"id": run_id},
            )
        return stats
    except Exception as exc:
        if gateway is not None and run_id is not None:
            try:
                gateway.update(
                    "vetmo_sync_runs",
                    {
                        "status": "error",
                        "finished_at": datetime.now(UTC).isoformat(),
                        **_optional_field(
                            include_trigger_source, "trigger_source", trigger,
                        ),
                        **_optional_field(
                            include_request_id, "request_id", request_id,
                        ),
                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                    },
                    {"id": run_id},
                )
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        client.close()


# ======================================================================
# Coordinated full sync (OpenDota meta + STRATZ matchups)
# ======================================================================

def sync_all(
    *,
    dry_run: bool = False,
    include_matchups: bool = True,
    ranks: range = range(0, 9),
    positions: range = range(0, 6),
    progress=print,
    trigger: str | None = None,
    request_id: str | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> SyncStats:
    """Полный sync: OpenDota мета + STRATZ матчапы.

    Порядок важен: сначала главная мета из OpenDota (патч, герои, win/pick/
    ban), затем контрпики/синергия из STRATZ. Если один источник падает,
    другой всё равно уже записан.
    """
    stats = SyncStats(source="combined")

    # 1) OpenDota: главная мета
    try:
        od_stats = sync_opendota_meta(
            dry_run=dry_run,
            trigger=trigger,
            request_id=request_id,
            progress=progress,
        )
        stats.patch_version = od_stats.patch_version
        stats.patch_id = od_stats.patch_id
        stats.rows_meta = od_stats.rows_meta
        stats.errors.extend(od_stats.errors)
        if od_stats.errors:
            progress("OpenDota часть завершена с ошибками")
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"opendota_meta: {type(exc).__name__}: {exc}")
        progress(f"ОШИБКА OpenDota мета: {type(exc).__name__}: {exc}")

    if should_stop is not None and should_stop():
        stats.errors.append("sync отменён пользователем")
        return stats

    # 2) STRATZ: только матчапы (+ опционально баны)
    if include_matchups and not (
        should_stop is not None and should_stop()
    ):
        try:
            sz_stats = sync_stratz_matchups(
                dry_run=dry_run,
                ranks=ranks,
                positions=positions,
                trigger=trigger,
                request_id=request_id,
                progress=progress,
                should_stop=should_stop,
            )
            stats.rows_matchups = sz_stats.rows_matchups
            stats.slices = sz_stats.slices
            stats.errors.extend(sz_stats.errors)
            if not stats.patch_version:
                stats.patch_version = sz_stats.patch_version
                stats.patch_id = sz_stats.patch_id
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"stratz_matchups: {type(exc).__name__}: {exc}")
            progress(f"ОШИБКА STRATZ матчапы: {type(exc).__name__}: {exc}")

    if any("отменён" in e for e in stats.errors):
        stats.errors.append("sync отменён пользователем")

    return stats


def _supports_column(gateway: SupabaseGateway, column: str) -> bool:
    """Проверяет, применена ли миграция с колонкой ``vetmo_sync_runs``.

    На удалённой БД колонки ``trigger_source``/``request_id`` могут
    отсутствовать. Тогда не роняем sync: значения сохраняются в
    ``details`` (jsonb), а отдельное поле пишется только после миграции.
    """
    try:
        gateway.select("vetmo_sync_runs", columns=column, limit=1)
    except Exception as exc:  # noqa: BLE001 - отличаем отсутствие колонки от сети
        message = str(exc)
        if column in message and ("42703" in message or "PGRST204" in message):
            logger.warning(
                "vetmo_sync_runs.%s отсутствует; значение будет сохранено в details",
                column,
            )
            return False
        raise
    return True


def _optional_field(include: bool, name: str, value: str | None) -> dict[str, str]:
    """Поле для payload, только если колонка существует и значение задано."""
    if include and value:
        return {name: value}
    return {}


def _trace_details(trigger: str | None, request_id: str | None) -> dict[str, str]:
    """Трассировка запуска для ``details`` (работает без миграции)."""
    details: dict[str, str] = {}
    if trigger:
        details["trigger_source"] = trigger
    if request_id:
        details["request_id"] = request_id
    return details


__all__ = [
    "SyncStats",
    "sync_all",
    "sync_opendota_meta",
    "sync_stratz_matchups",
]
