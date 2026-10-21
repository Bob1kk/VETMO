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
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import Any

from vetmo.data.supabase_heroes import load_seed_heroes
from vetmo.domain.rank_brackets import ALL_BRACKET, BASIC_BRACKETS
from vetmo.infra.config import Settings
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.infra.sync_settings import SyncSettings
from vetmo.services.stratz_aggregate import (
    _day_index,
    aggregate_hero_stats_week,
    ban_rates_by_rank,
    ban_stats_rows,
    hero_rows,
    matchup_bracket_rows,
    patch_rows,
    snapshot_rows,
)
from vetmo.services.stratz_client import StratzClient, StratzError

logger = logging.getLogger("vetmo.sync")

def _week_start_timestamp(now: datetime | None = None) -> int:
    """Начало текущей недели STRATZ (четверг 00:00 UTC).

    ``stats(week=...)`` и ``matchUp(week=...)`` принимают unix-время начала
    недели. STRATZ группирует недели с четверга: 2026-10-15, 2026-10-08 и
    т.д. Для среды 2026-10-21 это 2026-10-15.
    """
    moment = now or datetime.now(UTC)
    day = moment.date()
    days_since_thursday = (day.weekday() - 3) % 7
    start = day - timedelta(days=days_since_thursday)
    return int(datetime.combine(start, dt_time.min, tzinfo=UTC).timestamp())


def _week_end_date(week_start: int) -> str:
    """Последний календарный день недели STRATZ (среда) в ISO."""
    end = datetime.fromtimestamp(week_start, UTC) + timedelta(days=6)
    return end.date().isoformat()


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
    include_trigger_source = (
        gateway is not None and _supports_column(gateway, "trigger_source")
    )
    include_request_id = gateway is not None and _supports_column(gateway, "request_id")
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

        # --- banDay: пер-геройные баны (один запрос на все срезы) ---
        # Окно банов — последние 7 доступных дней banDay. Оно совпадает с
        # текущей неделей stats (четверг–среда), а не с устаревшим winDay.
        ban_rates: dict[int, dict[int, float]] = {}
        ban_deltas: dict[int, dict[int, float]] = {}
        if not stop_requested():
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

        # --- stats: свежая текущая неделя, позиции и группы рангов ---
        # winDay в октябре 2026 заканчивался 2026-10-10, а stats отдаёт
        # текущую неделю (2026-10-15…21) и сразу позиции + ранги.
        week_start = _week_start_timestamp()
        week_end = _week_end_date(week_start)
        snapshot_date = min(
            datetime.now(UTC).date().isoformat(), week_end,
        )
        stats_current: list[dict[str, Any]] = []
        stats_previous: list[dict[str, Any]] = []
        if not stop_requested():
            try:
                stats_current = client.hero_stats_week(week_start)
                progress(
                    f"  stats неделя {snapshot_date}: {len(stats_current)} строк"
                )
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(
                    f"stats current: {type(exc).__name__}: {exc}")
                progress(
                    f"  ОШИБКА stats current: {type(exc).__name__}: {exc}"
                )
        if stats_current and not stop_requested():
            try:
                stats_previous = client.hero_stats_week(
                    week_start - 7 * 86400,
                )
            except Exception as exc:  # noqa: BLE001 - дельты не критичны
                progress(
                    f"  предупреждение stats previous: {type(exc).__name__}: {exc}"
                )

        if stats_current:
            rows = aggregate_hero_stats_week(
                stats_current,
                patch_id=current_id,
                ranks=ranks,
                positions=positions,
                previous_rows=stats_previous,
                ban_rates=ban_rates,
                ban_deltas=ban_deltas,
            )
            stats.slices = len({
                (row["rank_tier"], row["position"]) for row in rows
            })
            stats.rows_meta = len(rows)
            stats.period = snapshot_date
            if gateway is not None and rows:
                by_rank: dict[int, list[dict[str, Any]]] = {}
                for row in rows:
                    by_rank.setdefault(int(row["rank_tier"]), []).append(row)
                for rank, rank_rows in sorted(by_rank.items()):
                    try:
                        _upsert(
                            gateway, "vetmo_meta", rank_rows,
                            "patch_id,hero_id,rank_tier,position,game_mode,window_days",
                        )
                    except Exception as exc:  # noqa: BLE001
                        stats.errors.append(
                            f"rank={rank} meta: {type(exc).__name__}: {exc}")
                    try:
                        _upsert(
                            gateway, "vetmo_snapshots",
                            snapshot_rows(rank_rows, snapshot_date),
                            "snapshot_date,patch_id,hero_id,rank_tier,position,game_mode,window_days",
                        )
                    except Exception as exc:  # noqa: BLE001
                        stats.errors.append(
                            f"rank={rank} snapshot: {type(exc).__name__}: {exc}")
            progress(
                f"  мета: {len(rows)} строк, {stats.slices} срезов, "
                f"период до {snapshot_date}"
            )
        elif not stats.errors:
            stats.errors.append("stats: текущая неделя пуста")

        # --- matchUp: матчапы за ту же текущую неделю ---
        if include_matchups and not stop_requested():
            hero_ids = [hero.id for hero in load_seed_heroes()]
            specs: list[tuple[str, str | None]] = [(ALL_BRACKET, None)]
            specs.extend((bracket, bracket) for bracket in BASIC_BRACKETS)
            fetched: list[dict[str, Any]] = []
            failed_brackets: list[str] = []
            for rank_bracket, bracket in specs:
                if stop_requested():
                    break
                try:
                    groups = client.matchup_groups(
                        hero_ids, take=300, week=week_start, bracket=bracket,
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
                    **_optional_field(
                        include_trigger_source, "trigger_source", trigger,
                    ),
                    **_optional_field(
                        include_request_id, "request_id", request_id,
                    ),
                    "details": {
                        "slices": stats.slices,
                        "period_end": stats.period,
                        "week_start": datetime.fromtimestamp(
                            week_start, UTC,
                        ).date().isoformat(),
                        "week_end": week_end,
                        "source": "stats+banDay+matchUp",
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


__all__ = ["SyncStats", "sync_all"]
