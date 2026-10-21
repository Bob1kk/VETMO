"""Sync STRATZ -> Supabase (service_role), отдельно от приложения.

Запуск:
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --dry-run
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py

Приложение никогда не получает service_role: скрипт читает его из
%APPDATA%/VETMO/secrets.env.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from vetmo.data.supabase_heroes import load_seed_heroes
from vetmo.domain.rank_brackets import ALL_BRACKET, BASIC_BRACKETS
from vetmo.infra.config import Settings
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.infra.sync_settings import SyncSettings
from vetmo.services.stratz_aggregate import (
    _day_index,
    aggregate_win_day,
    ban_rates_by_rank,
    ban_scope_for_rank,
    ban_stats_rows,
    hero_rows,
    matchup_bracket_rows,
    patch_rows,
    snapshot_rows,
    window_totals,
)
from vetmo.services.stratz_client import StratzClient, StratzError

logger = logging.getLogger("vetmo.sync")

RANK_BRACKETS: dict[int, str] = {
    1: "HERALD",
    2: "GUARDIAN",
    3: "CRUSADER",
    4: "ARCHON",
    5: "LEGEND",
    6: "ANCIENT",
    7: "DIVINE",
    8: "IMMORTAL",
}


def _week_start_timestamp(period: str | None) -> int | None:
    """Начало последней полной недели для ``matchUp(week:)``.

    ``winDay`` заканчивается, например, 2026-10-10. STRATZ ``week`` —
    unix-время начала недели; передаём 2026-10-04, чтобы получить
    ровно те же 7 дней, что и мета (04.10–10.10), а не неполную/пустую
    следующую неделю.
    """
    if not period:
        return None
    try:
        end = datetime.fromisoformat(str(period)).replace(tzinfo=UTC)
    except ValueError:
        return None
    end_day = int(end.timestamp() // 86400)
    return max(0, end_day - 6) * 86400


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


def _service_gateway(sync: SyncSettings) -> SupabaseGateway:
    settings = Settings(
        supabase_url=sync.supabase_url,
        supabase_anon_key=sync.service_key,
    )
    return SupabaseGateway(settings)


def _upsert(gateway: SupabaseGateway, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
    if rows:
        gateway.upsert(table, rows, on_conflict=conflict)


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
    """Выполняет полный sync reference-данных.

    ``should_stop`` опрашивается между срезами (ранги, позиции, брекеты
    матчапов). Отмена кооперативная: текущий запрос завершается, уже
    записанные строки остаются в БД, а ``errors`` пополняется сообщением
    ``"sync отменён пользователем"``.
    """
    sync = SyncSettings.load()
    client = StratzClient(sync.stratz_token)
    stats = SyncStats()
    gateway = None if dry_run else _service_gateway(sync)
    run_id: int | None = None
    cancelled = False

    def stop_requested() -> bool:
        """Один раз фиксирует отмену и сообщает о ней в лог."""
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
            run = gateway.insert("vetmo_sync_runs", [{
                "status": "running", "source": "stratz",
                "patch_version": current_name,
                "trigger_source": trigger,
                "request_id": request_id,
            }])
            run_id = int(run[0]["id"]) if run else None

        # --- banDay: пер-геройные баны (один запрос на все срезы) ---
        # Окно банов выравниваем по последнему дню winDay, чтобы карточка
        # меты была согласована (WR и баны за один и тот же период).
        ban_rates: dict[int, dict[int, float]] = {}
        ban_deltas: dict[int, dict[int, float]] = {}
        prefetched: dict[tuple[int, int], list[dict[str, Any]]] = {}
        if gateway is not None and not stop_requested():
            try:
                preview = client.win_day(bracket=None, position=0)
                prefetched[(0, 0)] = preview
                preview_days = [
                    day for day in (_day_index(row.get("day")) for row in preview)
                    if day is not None
                ]
                end_day = max(preview_days) if preview_days else None
                ban_raw = client.ban_day(days=30)
                ban_rates, ban_deltas = ban_rates_by_rank(
                    ban_raw, end_day=end_day,
                )
                diag = ban_stats_rows(
                    ban_raw, patch_id=current_id, end_day=end_day,
                )
                if diag:
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

        for rank in ranks:
            if stop_requested():
                break
            bracket = RANK_BRACKETS.get(rank)
            raw_by_position: dict[int, list[dict[str, Any]]] = {}
            # Сначала позиции 1..5: их сумма нужна для доли героя на позиции.
            for position in [p for p in positions if p != 0]:
                if stop_requested():
                    break
                try:
                    raw_by_position[position] = client.win_day(
                        bracket=bracket, position=position,
                    )
                except Exception as exc:  # noqa: BLE001
                    message = f"rank={rank} pos={position}: {type(exc).__name__}: {exc}"
                    stats.errors.append(message)
                    progress(f"  ОШИБКА {message}")
                time.sleep(0.1)
            totals: dict[int, int] = {}
            for _raw in raw_by_position.values():
                for hero_id, matches in window_totals(_raw).items():
                    totals[hero_id] = totals.get(hero_id, 0) + matches
            ordered_positions = [p for p in positions if p != 0]
            if 0 in positions:
                ordered_positions.append(0)
            for position in ordered_positions:
                if stop_requested():
                    break
                try:
                    raw: list[dict[str, Any]] = (
                        raw_by_position.get(position)
                        or prefetched.get((rank, position))
                        or []
                    )
                    if not raw:
                        raw = client.win_day(bracket=bracket, position=position)
                    assert isinstance(raw, list)
                    rows, snapshot_date = aggregate_win_day(
                        raw,
                        patch_id=current_id,
                        rank_tier=rank,
                        position=position,
                        hero_totals=totals if position > 0 else None,
                        ban_rates=ban_rates.get(rank),
                        ban_deltas=ban_deltas.get(rank),
                        ban_scope=ban_scope_for_rank(rank),
                    )
                    stats.slices += 1
                    if rows:
                        stats.rows_meta += len(rows)
                        if snapshot_date:
                            stats.period = snapshot_date
                        if gateway is not None and snapshot_date:
                            try:
                                _upsert(
                                    gateway, "vetmo_meta", rows,
                                    "patch_id,hero_id,rank_tier,position,game_mode,window_days",
                                )
                            except Exception as exc:  # noqa: BLE001
                                stats.errors.append(
                                    f"rank={rank} pos={position} meta: {type(exc).__name__}: {exc}")
                            try:
                                _upsert(
                                    gateway, "vetmo_snapshots",
                                    snapshot_rows(rows, snapshot_date),
                                    "snapshot_date,patch_id,hero_id,rank_tier,position,game_mode,window_days",
                                )
                            except Exception as exc:  # noqa: BLE001 - кэш схемы может быть устаревшим
                                stats.errors.append(
                                    f"rank={rank} pos={position} snapshot: {type(exc).__name__}: {exc}")
                    progress(
                        f"  rank={rank} pos={position}: {len(rows)} строк"
                        + (f", период до {snapshot_date}" if snapshot_date else "")
                    )
                except Exception as exc:  # noqa: BLE001 - один срез не рушит sync
                    message = f"rank={rank} pos={position}: {type(exc).__name__}: {exc}"
                    stats.errors.append(message)
                    progress(f"  ОШИБКА {message}")
                time.sleep(0.1)

        if include_matchups and not stop_requested():
            heroes = load_seed_heroes()
            hero_ids = [hero.id for hero in heroes]
            week = _week_start_timestamp(stats.period)
            specs: list[tuple[str, str | None]] = [(ALL_BRACKET, None)]
            specs.extend((bracket, bracket) for bracket in BASIC_BRACKETS)
            fetched: list[dict[str, Any]] = []
            failed_brackets: list[str] = []
            for rank_bracket, bracket in specs:
                if stop_requested():
                    break
                try:
                    groups = client.matchup_groups(
                        hero_ids, take=300, week=week, bracket=bracket,
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
            if gateway is not None and cancelled:
                # Частичные матчапы писать нельзя: delete+upsert заменил бы
                # прошлый полный срез неполным.
                stats.errors.append("matchups: запись пропущена из-за отмены")
            elif gateway is not None and fetched and not failed_brackets:
                try:
                    # Полная замена матчапов патча: старые top-10 не должны
                    # оставаться, если герой выпал из десятки после обновления.
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
                    "trigger_source": trigger,
                    "request_id": request_id,
                    "details": {
                        "slices": stats.slices,
                        "period_end": stats.period,
                        "cancelled": cancelled,
                        "errors": stats.errors[:20],
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
                        "trigger_source": trigger,
                        "request_id": request_id,
                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                    },
                    {"id": run_id},
                )
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        client.close()


__all__ = ["RANK_BRACKETS", "SyncStats", "sync_all"]
