"""Мета-данные из Supabase (STRATZ sync) без SQLAlchemy.

UI получает уже агрегированные строки через RPC ``vetmo_get_meta_report``.
Позиции в строке — только популярные позиции героя; детали для тултипа
собираются из ``vetmo_meta`` (is_popular = true).
"""

from __future__ import annotations

import logging
from typing import Any

from vetmo.domain.meta_row import MetaRow, PatchInfo, PositionStat
from vetmo.domain.models import Hero
from vetmo.domain.rank_brackets import basic_bracket_for_rank
from vetmo.infra.config import Settings
from vetmo.infra.supabase_gateway import SupabaseGateway

logger = logging.getLogger("vetmo.meta")

_META_COLUMNS = (
    "hero_id,name,internal_name,icon_url,primary_attr,attack_type,"
    "win_rate,delta_win,pick_rate,delta_pick,ban_rate,delta_ban,"
    "positions,patch_version,match_count,ban_scope"
)

# Порог, при котором метрика считается надёжной (совпадает с sync STRATZ).
_MIN_RELIABLE_MATCHES = 50


def _sample_reliable(row: dict[str, Any], match_count: int) -> bool:
    """Флаг из БД; для старых RPC без колонки — вывод из размера выборки."""
    raw = row.get("sample_reliable")
    if raw is not None:
        return bool(raw)
    return match_count >= _MIN_RELIABLE_MATCHES

_POSITION_COLUMNS = (
    "hero_id,position,pick_share,win_rate,match_count,is_popular"
)

# Прямой select вместо RPC: RPC с p_rank_tier=0/p_position=0 на Supabase
# выполняется десятки секунд (агрегат popular по всей таблице), из-за чего
# мета-отчёт и оверлей «зависали». Прямые select по индексу — доли секунды.
_META_ROW_COLUMNS = (
    "hero_id,position,rank_tier,win_rate,pick_rate,ban_rate,pick_share,"
    "match_count,delta_win,delta_pick,delta_ban,is_popular,ban_scope"
)

_HERO_COLUMNS = (
    "id,name,localized_name,icon_url,primary_attr,attack_type,roles"
)

# Ранги 1..8: в БД нет per-position строк для rank_tier=0, поэтому срез
# «Все ранги + позиция» собирается из восьми быстрых запросов (по одному
# на ранг) и агрегируется по match_count.
_ALL_RANKS = (1, 2, 3, 4, 5, 6, 7, 8)

# Позиции героя почти не зависят от ранга, поэтому для rank_tier=0 (где
# per-position строк нет) берём один быстрый срез Immortal. Пять запросов
# «все ранги + позиция» иногда упираются в троттлинг Supabase (20+ с), а
# один ранг — доли секунды.
_POSITION_REFERENCE_RANK = 8


def _weighted_avg(rows: list[dict[str, Any]], field: str) -> float | None:
    """Взвешенное по match_count среднее поля (None, если данных нет)."""
    total = 0
    acc = 0.0
    for row in rows:
        value = _as_float(row.get(field))
        if value is None:
            continue
        weight = max(_as_int(row.get("match_count")) or 0, 1)
        total += weight
        acc += value * weight
    if total <= 0:
        return None
    return round(acc / total, 2)


def _match_count(rows: list[dict[str, Any]]) -> int:
    return sum(_as_int(row.get("match_count")) or 0 for row in rows)


def _details_from_grouped(
    grouped: dict[int, list[dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    """position -> {pick_share, win_rate, match_count} из строк по рангам."""
    return {
        pos: {
            "pick_share": _weighted_avg(items, "pick_share"),
            "win_rate": _weighted_avg(items, "win_rate"),
            "match_count": _match_count(items),
        }
        for pos, items in grouped.items()
    }


def _group_rows(
    rows: list[dict[str, Any]],
) -> dict[int, dict[int, list[dict[str, Any]]]]:
    """hero_id -> position -> строки (по рангам)."""
    grouped: dict[int, dict[int, list[dict[str, Any]]]] = {}
    for row in rows:
        hero_id = _as_int(row.get("hero_id"))
        pos = _as_int(row.get("position"))
        if hero_id is None or pos is None or pos <= 0:
            continue
        grouped.setdefault(hero_id, {}).setdefault(pos, []).append(row)
    return grouped


def _aggregate_all_ranks(
    grouped: dict[int, dict[int, list[dict[str, Any]]]], position: int,
) -> list[dict[str, Any]]:
    """Строки среза «все ранги + позиция», взвешенные по match_count."""
    result: list[dict[str, Any]] = []
    for hero_id, by_pos in grouped.items():
        items = by_pos.get(position)
        if not items:
            continue
        best = max(items, key=lambda row: _as_int(row.get("match_count")) or 0)
        result.append({
            "hero_id": hero_id,
            "position": position,
            "win_rate": _weighted_avg(items, "win_rate"),
            "pick_rate": _weighted_avg(items, "pick_rate"),
            "ban_rate": _weighted_avg(items, "ban_rate"),
            "delta_win": _weighted_avg(items, "delta_win"),
            "delta_pick": _weighted_avg(items, "delta_pick"),
            "delta_ban": _weighted_avg(items, "delta_ban"),
            "match_count": _match_count(items),
            "ban_scope": best.get("ban_scope"),
            "positions": sorted(by_pos),
            "position_details": _details_from_grouped(by_pos),
        })
    return result


def _enrich_with_heroes(
    rows: list[dict[str, Any]],
    heroes: dict[int, dict[str, Any]],
    patch_version: str | None,
) -> list[dict[str, Any]]:
    """Добавляет к строкам меты имя/иконку/атрибуты из каталога героев."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        hero_id = _as_int(row.get("hero_id"))
        hero = heroes.get(hero_id) if hero_id is not None else None
        if hero_id is None or hero is None:
            continue
        enriched.append({
            "hero_id": hero_id,
            "name": hero.get("localized_name") or hero.get("name") or "",
            "internal_name": hero.get("name") or "",
            "icon_url": hero.get("icon_url") or "",
            "primary_attr": hero.get("primary_attr") or "",
            "attack_type": hero.get("attack_type") or "",
            "roles": hero.get("roles") or [],
            "win_rate": row.get("win_rate"),
            "delta_win": row.get("delta_win"),
            "pick_rate": row.get("pick_rate"),
            "delta_pick": row.get("delta_pick"),
            "ban_rate": row.get("ban_rate"),
            "delta_ban": row.get("delta_ban"),
            "positions": row.get("positions") or [],
            "position_details": row.get("position_details") or {},
            "patch_version": patch_version,
            "match_count": row.get("match_count") or 0,
            "ban_scope": row.get("ban_scope"),
        })
    return enriched


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _positions(value: object) -> list[int]:
    """PostgREST smallint[] может прийти list или строкой '{1,2}'."""
    if isinstance(value, (list, tuple)):
        raw = value
    elif isinstance(value, str):
        raw = value.strip("{}").split(",") if value.strip("{}") else []
    else:
        raw = []
    result: set[int] = set()
    for item in raw:
        number = _as_int(item)
        if number is not None and 1 <= number <= 5:
            result.add(number)
    return sorted(result)


def _hero_from_row(row: dict[str, Any]) -> Hero:
    return Hero(
        id=int(row["hero_id"]),
        name=str(row.get("internal_name") or f"hero_{row['hero_id']}"),
        localized_name=str(row.get("name") or row.get("internal_name") or ""),
        primary_attr=str(row.get("primary_attr") or ""),
        attack_type=str(row.get("attack_type") or ""),
        roles=[str(role) for role in (row.get("roles") or [])],
        icon_url=str(row.get("icon_url") or "") or None,
        is_validated=True,
    )


def _position_details(value: object) -> dict[int, PositionStat]:
    """JSONB из RPC -> dict[int, PositionStat]."""
    if not isinstance(value, dict):
        return {}
    result: dict[int, PositionStat] = {}
    for key, raw in value.items():
        position = _as_int(key)
        if position is None or not 1 <= position <= 5 or not isinstance(raw, dict):
            continue
        result[position] = PositionStat(
            position=position,
            pick_share=_as_float(raw.get("pick_share")),
            win_rate=_as_float(raw.get("win_rate")),
            match_count=_as_int(raw.get("match_count")) or 0,
        )
    return result


def _to_meta_row(row: dict[str, Any]) -> MetaRow:
    hero = _hero_from_row(row)
    details = _position_details(row.get("position_details"))
    match_count = _as_int(row.get("match_count")) or 0
    return MetaRow(
        hero_id=hero.id,
        name=hero.localized_name or hero.name,
        hero=hero,
        win_rate=_as_float(row.get("win_rate")) or 0.0,
        delta_win=_as_float(row.get("delta_win")),
        pick_rate=_as_float(row.get("pick_rate")) or 0.0,
        delta_pick=_as_float(row.get("delta_pick")),
        ban_rate=_as_float(row.get("ban_rate")),
        delta_ban=_as_float(row.get("delta_ban")),
        positions=_positions(row.get("positions")) or sorted(details),
        position_stats=details,
        patch_version=str(row.get("patch_version") or "") or None,
        match_count=match_count,
        ban_scope=str(row.get("ban_scope") or "") or None,
        sample_reliable=_sample_reliable(row, match_count),
    )


class SupabaseMetaService:
    """Патчи, строки меты, позиции и матчапы из Supabase."""

    def __init__(self, gateway: SupabaseGateway, settings: Settings) -> None:
        self._gateway = gateway
        self._settings = settings
        self._patches_cache: list[PatchInfo] | None = None
        self._meta_cache: dict[tuple, list[MetaRow]] = {}
        self._matchup_cache: dict[int, list[dict[str, Any]]] = {}
        self._matchup_highlight_cache: dict[
            tuple[int, int, str],
            tuple[str, dict[str, list[dict[str, Any]]], bool],
        ] = {}
        self._last_period_end: str | None = None
        self._hero_rows_cache: dict[int, dict[str, Any]] | None = None
        self._positions_cache: dict[
            tuple[int, int, str], dict[int, dict[int, PositionStat]],
        ] = {}

    @property
    def period_end(self) -> str | None:
        """Фактическая последняя дата данных из STRATZ (например '2026-10-10')."""
        return self._last_period_end

    def get_period(self) -> str | None:
        """Человекочитаемый период данных, например '04.10 – 10.10.2026'."""
        if not self._last_period_end:
            return None
        try:
            from datetime import datetime, timedelta
            end = datetime.fromisoformat(self._last_period_end).date()
            start = end - timedelta(days=6)
            return f"{start:%d.%m} – {end:%d.%m.%Y}"
        except ValueError:
            return self._last_period_end

    # ------------------------------------------------------------- патчи --
    def get_patches(self, limit: int = 30) -> list[PatchInfo]:
        """Список патчей для поиска/выбора (свежие сверху)."""
        if self._patches_cache is not None:
            return list(self._patches_cache[:limit])
        if not self._gateway.is_configured:
            return []
        try:
            rows = self._gateway.select(
                "vetmo_patches",
                columns="id,version,release_date,is_current",
                order=("id", True),
                limit=max(1, limit),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Патчи из Supabase недоступны: %s", type(exc).__name__)
            return []
        patches = [
            PatchInfo(
                id=int(row["id"]),
                version=str(row.get("version") or ""),
                release_date=str(row.get("release_date") or "") or None,
                is_current=bool(row.get("is_current")),
            )
            for row in rows
            if row.get("id") is not None and row.get("version")
        ]
        self._patches_cache = patches
        return patches[:limit]

    def latest_patch(self) -> PatchInfo | None:
        """Текущий патч (is_current) либо самый свежий из доступных."""
        patches = self.get_patches(limit=30)
        current = next((p for p in patches if p.is_current), None)
        return current or (patches[0] if patches else None)

    def find_patch(self, patch_id: int | None = None) -> PatchInfo | None:
        """Патч по id или текущий."""
        if patch_id is None:
            return self.latest_patch()
        return next((p for p in self.get_patches(limit=100) if p.id == patch_id), None)

    def invalidate(self) -> None:
        """Сбрасывает кэши после обновления данных."""
        self._patches_cache = None
        self._meta_cache.clear()
        self._matchup_cache.clear()
        self._matchup_highlight_cache.clear()
        self._hero_rows_cache = None
        self._positions_cache.clear()

    # ------------------------------------------------------------- мета ----
    def get_meta_rows(
        self,
        *,
        patch_id: int | None = None,
        rank_tier: int | None = None,
        position: int | None = None,
        limit: int = 200,
    ) -> list[MetaRow]:
        """Строки мета-отчёта для выбранного среза."""
        patch = self.find_patch(patch_id)
        if patch is None:
            return []
        rank = int(rank_tier) if rank_tier is not None and 0 <= int(rank_tier) <= 8 else 0
        pos = int(position) if position is not None and 1 <= int(position) <= 5 else 0
        key = (patch.id, rank, pos, int(limit))
        cached = self._meta_cache.get(key)
        if cached is not None:
            return list(cached)
        if not self._gateway.is_configured:
            return []
        try:
            if rank == 0:
                # Быстрый путь: RPC для «все ранги» на Supabase считается
                # десятки секунд, прямые select — доли секунды.
                data = self._direct_meta_rows(patch, rank, pos, limit)
            else:
                data = self._gateway.rpc(
                    "vetmo_get_meta_report",
                    {
                        "p_patch_id": patch.id,
                        "p_rank_tier": rank,
                        "p_position": pos,
                        "p_window_days": int(self._settings.meta_window_days),
                        "p_limit": max(0, int(limit)),
                    },
                )
        except Exception as exc:  # noqa: BLE001 - показываем пустое состояние
            logger.warning("Мета-срез не получен: %s", type(exc).__name__)
            data = None
        if isinstance(data, dict):
            data = [data]
        rows = [
            _to_meta_row(row)
            for row in (data or [])
            if isinstance(row, dict) and row.get("hero_id") is not None
        ]
        if rank > 0 and rows and any(not row.position_stats for row in rows):
            self._attach_position_stats(rows, patch.id, rank)
        self._meta_cache[key] = rows
        # Запоминаем факттический период данных (однажды, при первом erfolgreich вызове)
        if self._last_period_end is None:
            try:
                snap_rows = self._gateway.select(
                    "vetmo_snapshots",
                    columns="snapshot_date",
                    order=("snapshot_date", True),
                    limit=1,
                )
                if snap_rows:
                    self._last_period_end = str(snap_rows[0]["snapshot_date"])
            except Exception:  # noqa: BLE001 - период не критичен
                pass
        return list(rows)

    def _direct_meta_rows(
        self, patch: PatchInfo, rank: int, pos: int, limit: int,
    ) -> list[dict[str, Any]]:
        """Строки меты прямыми select (без медленного RPC)."""
        window = int(self._settings.meta_window_days)
        if rank == 0 and pos > 0:
            # В БД нет per-position строк для rank_tier=0: собираем срез
            # «все ранги + позиция» одним запросом по рангам 1..8 и
            # агрегируем по match_count на клиенте.
            rows = self._gateway.select(
                "vetmo_meta",
                columns=_META_ROW_COLUMNS,
                filters={
                    "patch_id": patch.id,
                    "rank_tier": ("in", list(_ALL_RANKS)),
                    "position": pos,
                    "window_days": window,
                    "game_mode": "ALL_PICK_RANKED",
                    "is_popular": True,
                },
                limit=5000,
            )
            aggregated = _aggregate_all_ranks(_group_rows(rows), pos)
            aggregated.sort(
                key=lambda row: (
                    -(_as_float(row.get("win_rate")) or 0.0),
                    _as_int(row.get("hero_id")) or 0,
                ),
            )
            rows = aggregated[: max(0, int(limit))]
        else:
            filters: dict[str, Any] = {
                "patch_id": patch.id,
                "rank_tier": rank,
                "position": pos,
                "window_days": window,
                "game_mode": "ALL_PICK_RANKED",
            }
            if pos > 0:
                filters["is_popular"] = True
            rows = self._gateway.select(
                "vetmo_meta",
                columns=_META_ROW_COLUMNS,
                filters=filters,
                order=("win_rate", True),
                limit=max(1, int(limit)),
            )
        enriched = _enrich_with_heroes(rows, self._hero_rows(), patch.version)
        if rank == 0:
            # В rank_tier=0 нет per-position строк — позиции берём из
            # быстрого среза Immortal, иначе фильтр рекомендаций пуст.
            self._attach_positions_index(enriched, patch.id)
        return enriched

    def _positions_index(
        self, patch_id: int,
    ) -> dict[int, dict[int, PositionStat]]:
        """hero_id -> position -> PositionStat из одного быстрого среза.

        Нужен для rank_tier=0: там per-position строк нет, и без индекса
        фильтр рекомендаций пропускал carry-героев на позицию 5.
        """
        key = (int(patch_id), int(self._settings.meta_window_days), "ALL_PICK_RANKED")
        cached = self._positions_cache.get(key)
        if cached is not None:
            return cached
        if not self._gateway.is_configured:
            return {}
        try:
            rows = self._gateway.select(
                "vetmo_meta",
                columns=_POSITION_COLUMNS,
                filters={
                    "patch_id": key[0],
                    "rank_tier": _POSITION_REFERENCE_RANK,
                    "window_days": key[1],
                    "game_mode": key[2],
                    "is_popular": True,
                    "position": ("in", [1, 2, 3, 4, 5]),
                },
                limit=2000,
            )
        except Exception as exc:  # noqa: BLE001 - без индекса фильтр слабее
            logger.warning("Позиции героев не получены: %s", type(exc).__name__)
            return {}
        index: dict[int, dict[int, PositionStat]] = {}
        for row in rows:
            hero_id = _as_int(row.get("hero_id"))
            pos = _as_int(row.get("position"))
            if hero_id is None or pos is None or not 1 <= pos <= 5:
                continue
            index.setdefault(hero_id, {})[pos] = PositionStat(
                position=pos,
                pick_share=_as_float(row.get("pick_share")),
                win_rate=_as_float(row.get("win_rate")),
                match_count=_as_int(row.get("match_count")) or 0,
            )
        self._positions_cache[key] = index
        return index

    def _attach_positions_index(
        self, rows: list[dict[str, Any]], patch_id: int,
    ) -> None:
        """Добавляет позиции героев туда, где их нет (срез rank_tier=0)."""
        index = self._positions_index(patch_id)
        if not index:
            return
        for row in rows:
            hero_id = _as_int(row.get("hero_id"))
            details = index.get(hero_id) if hero_id is not None else None
            if not details:
                continue
            if not row.get("positions"):
                row["positions"] = sorted(details)
            if not row.get("position_details"):
                row["position_details"] = {
                    pos: {
                        "pick_share": stat.pick_share,
                        "win_rate": stat.win_rate,
                        "match_count": stat.match_count,
                    }
                    for pos, stat in details.items()
                }

    def _hero_rows(self) -> dict[int, dict[str, Any]]:
        """Каталог героев (id -> строка) для склейки с метой; кэш в памяти."""
        if self._hero_rows_cache is None:
            try:
                rows = self._gateway.select(
                    "vetmo_heroes", columns=_HERO_COLUMNS, limit=500,
                )
            except Exception:  # noqa: BLE001 - без имён строки не построить
                rows = []
            self._hero_rows_cache = {
                int(row["id"]): row
                for row in rows
                if row.get("id") is not None
            }
        return self._hero_rows_cache

    def _attach_position_stats(
        self, rows: list[MetaRow], patch_id: int, rank: int,
    ) -> None:
        """Добавляет position_stats (pick_share/WR/матчи) для тултипов."""
        if not rows:
            return
        try:
            data = self._gateway.select(
                "vetmo_meta",
                columns=_POSITION_COLUMNS,
                filters={
                    "patch_id": patch_id,
                    "rank_tier": rank,
                    "window_days": int(self._settings.meta_window_days),
                    "game_mode": "ALL_PICK_RANKED",
                    "is_popular": True,
                    "position": ("in", [1, 2, 3, 4, 5]),
                },
                limit=1000,
            )
        except Exception:  # noqa: BLE001 - тултип не критичен
            return
        by_hero: dict[int, dict[int, PositionStat]] = {}
        for row in data:
            hero_id = _as_int(row.get("hero_id"))
            pos = _as_int(row.get("position"))
            if hero_id is None or pos is None:
                continue
            by_hero.setdefault(hero_id, {})[pos] = PositionStat(
                position=pos,
                pick_share=_as_float(row.get("pick_share")),
                win_rate=_as_float(row.get("win_rate")),
                match_count=_as_int(row.get("match_count")) or 0,
            )
        for row in list(rows):  # type: ignore[assignment]
            details = by_hero.get(row.hero_id)  # type: ignore[attr-defined]
            if details:
                row.position_stats = details  # type: ignore[attr-defined]
                if not row.positions:  # type: ignore[attr-defined]
                    row.positions = sorted(details)  # type: ignore[attr-defined]

    def get_meta_map(
        self, *, rank_tier: int | None = None, patch_id: int | None = None,
    ) -> dict[int, MetaRow]:
        """hero_id -> MetaRow (all positions) для рекомендаций оверлея."""
        return {
            row.hero_id: row
            for row in self.get_meta_rows(
                patch_id=patch_id, rank_tier=rank_tier, position=None, limit=200,
            )
        }

    def get_meta_summary(self, limit: int = 10) -> tuple[str | None, list[MetaRow]]:
        """(версия патча, топ строк) — для NewsService.get_meta_summary."""
        patch = self.latest_patch()
        if patch is None:
            return None, []
        rows = self.get_meta_rows(patch_id=patch.id, limit=max(0, limit))
        return patch.version, rows

    # ---------------------------------------------------------- матчапы ----
    def get_matchups_bulk(
        self,
        hero_ids: list[int],
        vs_ids: list[int],
        patch_id: int | None = None,
    ) -> dict[int, list[dict[str, Any]]]:
        """Матчапы для набора героев против набора врагов — одним запросом."""
        patch = self.find_patch(patch_id)
        if patch is None or not hero_ids or not vs_ids:
            return {}
        try:
            rows = self._gateway.select(
                "vetmo_hero_matchups",
                columns="hero_id,vs_hero_id,win_rate,match_count",
                filters={
                    "patch_id": patch.id,
                    "hero_id": ("in", [int(h) for h in hero_ids]),
                    "vs_hero_id": ("in", [int(h) for h in vs_ids]),
                    "kind": "vs",
                    "rank_bracket": "ALL",
                },
                limit=5000,
            )
        except Exception:  # noqa: BLE001
            return {}
        result: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            hero_id = _as_int(row.get("hero_id"))
            if hero_id is not None:
                result.setdefault(hero_id, []).append(row)
        return result

    def get_matchups(self, hero_id: int, patch_id: int | None = None) -> list[dict[str, Any]]:
        """Все матчапы героя (vs, все ранги) для тултипа/рекомендаций."""
        patch = self.find_patch(patch_id)
        if patch is None:
            return []
        cache_key = int(hero_id)
        if cache_key in self._matchup_cache:
            return list(self._matchup_cache[cache_key])
        try:
            rows = self._gateway.select(
                "vetmo_hero_matchups",
                columns="vs_hero_id,win_rate,match_count,sample_reliable",
                filters={
                    "patch_id": patch.id,
                    "hero_id": int(hero_id),
                    "kind": "vs",
                    "rank_bracket": "ALL",
                },
                order=("win_rate", True),
                limit=200,
            )
        except Exception:  # noqa: BLE001
            return []
        self._matchup_cache[cache_key] = rows
        return list(rows)

    def _matchup_highlights(
        self,
        patch_id: int,
        hero_id: int,
        rank_bracket: str,
    ) -> list[dict[str, Any]]:
        """Top-10 highlights одного среза (counter/good/synergy)."""
        try:
            return self._gateway.select(
                "vetmo_hero_matchups",
                columns=(
                    "vs_hero_id,kind,rank_bracket,bucket,bucket_rank,"
                    "win_rate,match_count,sample_reliable"
                ),
                filters={
                    "patch_id": int(patch_id),
                    "hero_id": int(hero_id),
                    "rank_bracket": rank_bracket,
                    "bucket": ("in", ["counter", "good", "synergy"]),
                },
                order=("bucket_rank", False),
                limit=60,
            )
        except Exception:  # noqa: BLE001
            return []

    def get_matchup_highlights(
        self,
        hero_id: int,
        rank_tier: int = 0,
        patch_id: int | None = None,
    ) -> tuple[str, dict[str, list[dict[str, Any]]], bool]:
        """(фактическая группа, bucket -> строки, был ли fallback на ALL).

        Для ранговой группы сначала читаем её highlights. Если их нет
        (старый sync/пустой срез), честно отдаём общий срез и флаг fallback,
        чтобы UI подписал это, а не выдавал общие данные за ранговые.
        """
        patch = self.find_patch(patch_id)
        if patch is None:
            return "ALL", {}, False
        bracket = basic_bracket_for_rank(rank_tier)
        cache_key = (patch.id, int(hero_id), bracket)
        cached = self._matchup_highlight_cache.get(cache_key)
        if cached is not None:
            cached_actual, cached_grouped, cached_fallback = cached
            return cached_actual, {
                key: list(value) for key, value in cached_grouped.items()
            }, cached_fallback

        rows = self._matchup_highlights(patch.id, int(hero_id), bracket)
        actual = bracket
        fallback = False
        if not rows and bracket != "ALL":
            rows = self._matchup_highlights(patch.id, int(hero_id), "ALL")
            actual = "ALL"
            fallback = True

        grouped: dict[str, list[dict[str, Any]]] = {
            "counter": [], "good": [], "synergy": [],
        }
        for row in rows:
            bucket = str(row.get("bucket") or "")
            if bucket in grouped:
                grouped[bucket].append(row)
        for bucket in grouped:
            grouped[bucket].sort(
                key=lambda item: int(item.get("bucket_rank") or 999)
            )
            grouped[bucket] = grouped[bucket][:10]

        self._matchup_highlight_cache[cache_key] = (actual, grouped, fallback)
        return actual, {
            key: list(value) for key, value in grouped.items()
        }, fallback


__all__ = ["SupabaseMetaService"]
