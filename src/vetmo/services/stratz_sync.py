"""Sync STRATZ -> Supabase (service_role), отдельно от приложения.

Запуск:
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --dry-run
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py

Приложение никогда не получает service_role: скрипт читает его из
%APPDATA%/VETMO/secrets.env.

Подход согласован с прошлым бета-релизом:winDay с фильтром
gameModeIds=ALL_PICK_RANKED — данные совпадают с референсными сайтами
(dotabuff, opendota), в отличие от stats (без фильтра по режиму игры).
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
    ban_stats_rows,
    hero_rows,
    matchup_bracket_rows,
    patch_rows,
    snapshot_rows,
)
from vetmo.services.stratz_client import StratzClient, StratzError

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
    """Выполняет полный sync reference-данных через winDay (как в бета-релизе).

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

        # --- winDay: мета по дням, фильтр ALL_PICK_RANKED (как в бета-релизе) ---
        # winDay не поддерживает bracketIds (HTTP 400), поэтому загружаем
        # только rank 0 (все ранги) для каждой позиции. Бан-рейт по рангам
        # берётся из banDay (загружено выше).
        all_rows_meta: list[dict[str, Any]] = []
        slice_count = 0

        for position in positions:
            if stop_requested():
                break
            try:
                win_rows = client.win_day(
                    position=position if position > 0 else None,
                    take=3000,
                )
                progress(f"  winDay pos={position}: {len(win_rows)} строк")
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(
                    f"winDay pos={position}: {type(exc).__name__}: {exc}")
                progress(f"  ОШИБКА winDay pos={position}: "
                         f"{type(exc).__name__}: {exc}")
                continue

            rows_meta, snapshot_date = aggregate_win_day(
                win_rows,
                patch_id=current_id,
                rank_tier=0,
                position=position,
                ban_rates=ban_rates.get(0) if ban_rates else None,
                ban_deltas=ban_deltas.get(0) if ban_deltas else None,
                ban_scope="ALL",
            )
            all_rows_meta.extend(rows_meta)
            slice_count += 1
            if snapshot_date:
                stats.period = snapshot_date

            # Снимки — только для текущей позиции (rank 0).
            if gateway is not None and rows_meta and snapshot_date:
                try:
                    _upsert(
                        gateway, "vetmo_meta", rows_meta,
                        "patch_id,hero_id,rank_tier,position,game_mode,window_days",
                    )
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(
                        f"pos={position} meta: {type(exc).__name__}: {exc}")
                try:
                    _upsert(
                        gateway, "vetmo_snapshots",
                        snapshot_rows(rows_meta, snapshot_date),
                        "snapshot_date,patch_id,hero_id,rank_tier,position,game_mode,window_days",
                    )
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(
                        f"pos={position} snapshot: {type(exc).__name__}: {exc}")

            stats.rows_meta = len(all_rows_meta)
            stats.slices = slice_count
            time.sleep(0.1)

            if not rows_meta:
                stats.errors.append(
                    f"winDay pos={position}: пустой результат")

        # --- matchUp: матчапы за текущую неделю ---
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
                        "source": "winDay+banDay+matchUp",
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
