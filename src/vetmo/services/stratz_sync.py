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
from datetime import UTC, date, datetime, timedelta
from typing import Any

from vetmo.data.db import create_db
from vetmo.data.repositories.hero_repo import HeroRepository
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


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _upsert(gateway: SupabaseGateway, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
    if rows:
        gateway.upsert(table, rows, on_conflict=conflict)


def _resolve_patch(gateway: SupabaseGateway, patch_version: str) -> int:
    """Вернуть id патча в Supabase для версии OpenDota.

    OpenDota отдаёт базовую версию (``7.41``), а в Supabase текущий патч
    ``7.41f`` (id=190). Мапим по базовой версии, не создаём дубликат.
    """
    base = str(patch_version).split(" ")[0]
    patches = gateway.select(
        "vetmo_patches", columns="id,version,is_current", order=("id", True),
    )
    matching = [
        r for r in patches if str(r.get("version") or "").startswith(base)
    ]
    if matching:
        # Предпочитаем текущий, затем самый свежий по id.
        matching.sort(
            key=lambda r: (bool(r.get("is_current")), _as_int(r.get("id")) or 0),
            reverse=True,
        )
        return _as_int(matching[0]["id"]) or 0
    inserted = gateway.insert("vetmo_patches", [{
        "version": patch_version, "game_version_id": None,
        "release_date": None, "is_current": True, "source": "opendota",
    }])
    return _as_int(inserted[0]["id"]) or 0


def _previous_snapshot_map(
    gateway: SupabaseGateway, patch_id: int, snapshot_date: date,
) -> dict[tuple[int, int], dict[str, Any]]:
    """Словарь (hero_id, rank_tier) -> строка ближайшего снапшота не моложе 7 дней."""
    cutoff = (snapshot_date - timedelta(days=7)).isoformat()
    dates = gateway.select(
        "vetmo_snapshots", columns="snapshot_date",
        filters={
            "source": "opendota",
            "patch_id": patch_id,
            "snapshot_date": ("lte", cutoff),
        },
        order=("snapshot_date", True), limit=1,
    )
    if not dates:
        return {}
    prev_date = str(dates[0]["snapshot_date"])
    rows = gateway.select(
        "vetmo_snapshots", columns="hero_id,rank_tier,win_rate,pick_rate",
        filters={
            "source": "opendota",
            "patch_id": patch_id,
            "snapshot_date": prev_date,
        },
        limit=10000,
    )
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        hid = _as_int(row.get("hero_id"))
        rt = _as_int(row.get("rank_tier"))
        if hid is None or rt is None:
            continue
        result[(hid, rt)] = row
    return result


def sync_opendota_meta(
    *,
    dry_run: bool = False,
    trigger: str | None = None,
    request_id: str | None = None,
    progress=print,
) -> SyncStats:
    """Синхронизирует основную мету из OpenDota heroStats.

    Пишет в Supabase:
      * vetmo_heroes — справочник героев;
      * vetmo_patches — патч OpenDota, смapped на текущий патч Supabase
        по базовой версии (7.41 -> 7.41f);
      * vetmo_meta — по одной строке на (герой, ранг 0..7, позиция 0),
        window_days=7, source='opendota', ban_rate=None;
      * vetmo_snapshots — ежедневный снапшот для расчёта дельт.

    Дельты — относительное изменение (%) к ближайшему снапшоту не моложе
    7 дней назад (как в Dotabuff — сравнение с предыдущей неделей).
    Если история ещё не накопилась — ``None`` (отображается как «—»).

    Не требует токена API. service_role только для записи в Supabase.
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
        # --- Сырые heroStats (один запрос) ---
        raw = client.fetch_hero_stats()
        if not isinstance(raw, list) or not raw:
            raise RuntimeError("OpenDota heroStats пуст или недоступен")
        patch_version, patch_date = client.latest_patch()
        stats.patch_version = patch_version
        progress(f"OpenDota патч: {patch_version}; героев: {len(raw)}")

        # Поддерживаем локальную БД в актуальном состоянии (offline-резерв).
        client.sync_heroes(limit=0, data=raw)

        if gateway is None:
            return stats

        # --- Патч в Supabase: OpenDota 7.41 -> текущий 7.41f (id=190) ---
        patch_id = _resolve_patch(gateway, patch_version)
        stats.patch_id = patch_id
        progress(f"Supabase патч id={patch_id} ({patch_version})")

        # --- Герои -> vetmo_heroes ---
        with sessionmaker() as session:
            heroes = HeroRepository(session).get_all()
        if heroes:
            _upsert(gateway, "vetmo_heroes", hero_rows(heroes), "id")
            progress(f"  vetmo_heroes: {len(heroes)} строк")

        # --- Мета -> vetmo_meta ---
        total_pub_pick = sum(float(r.get("pub_pick") or 0) for r in raw)
        tier_totals = {
            tier: sum(float(r.get(f"{tier}_pick") or 0) for r in raw)
            for tier in range(1, 8)
        }
        totals = {0: total_pub_pick, **tier_totals}

        snapshot_date = datetime.now(UTC).date()
        meta_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []

        for record in raw:
            hero_id = _as_int(record.get("id"))
            if hero_id is None or hero_id <= 0:
                continue

            for rank_tier in (0, *range(1, 8)):
                if rank_tier == 0:
                    pick = float(record.get("pub_pick") or 0)
                    win = float(record.get("pub_win") or 0)
                    total = totals[0]
                else:
                    pick = float(record.get(f"{rank_tier}_pick") or 0)
                    win = float(record.get(f"{rank_tier}_win") or 0)
                    total = totals[rank_tier]
                if pick <= 0 or total <= 0:
                    continue

                win_rate = round(max(0.0, min(100.0, 100.0 * win / pick)), 2)
                pick_rate = round(max(0.0, min(100.0, 1000.0 * pick / total)), 2)
                match_count = int(pick)
                win_count = int(win)
                sample_reliable = match_count >= 50

                base = {
                    "patch_id": patch_id, "hero_id": hero_id,
                    "rank_tier": rank_tier, "position": 0,
                    "game_mode": "ALL_PICK_RANKED", "window_days": 7,
                    "match_count": match_count, "win_count": win_count,
                    "win_rate": win_rate, "pick_rate": pick_rate,
                    "ban_rate": None, "pick_share": None,
                    "is_popular": False, "sample_reliable": sample_reliable,
                    "delta_win": None, "delta_pick": None, "delta_ban": None,
                    "ban_scope": None, "source": "opendota",
                }
                meta_rows.append(dict(base))
                snapshot_rows.append({
                    "snapshot_date": snapshot_date.isoformat(), **base,
                })

        # --- Дельты: относительное изменение к снапшоту ~7 дней назад ---
        prev = _previous_snapshot_map(gateway, patch_id, snapshot_date)
        def _prev_float(row: dict[str, Any], key: str) -> float:
            try:
                return float(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        for row in meta_rows:
            key = (row["hero_id"], row["rank_tier"])
            if key not in prev:
                continue
            pw = _prev_float(prev[key], "win_rate")
            pp = _prev_float(prev[key], "pick_rate")
            cw = row["win_rate"]
            cp = row["pick_rate"]
            if pw and pw > 0:
                row["delta_win"] = round((cw - pw) / pw * 100.0, 2)
            if pp and pp > 0:
                row["delta_pick"] = round((cp - pp) / pp * 100.0, 2)

        # --- Запись в Supabase ---
        _upsert(
            gateway, "vetmo_meta", meta_rows,
            "patch_id,hero_id,rank_tier,position,game_mode,window_days",
        )
        progress(f"  vetmo_meta: {len(meta_rows)} строк")
        _upsert(
            gateway, "vetmo_snapshots", snapshot_rows,
            "snapshot_date,patch_id,hero_id,rank_tier,position,game_mode,window_days",
        )
        progress(f"  vetmo_snapshots: {len(snapshot_rows)} строк")
        stats.rows_meta = len(meta_rows)
        return stats

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
