"""Позиции героев для среза rank_tier=0 и фильтр рекомендаций.

В ``vetmo_meta`` нет per-position строк для rank_tier=0, поэтому позиции
берутся из одного быстрого среза Immortal. Без этого фильтр рекомендаций
пропускал carry-героев (Wraith King, Outworld Devourer) на позицию 5.
"""

from __future__ import annotations

from typing import Any

import pytest

from vetmo.domain.meta_row import MetaRow, PositionStat
from vetmo.domain.models import Hero
from vetmo.services.supabase_draft import SupabaseDraftService
from vetmo.services.supabase_meta import SupabaseMetaService


class _StubGateway:
    """Двойник SupabaseGateway: отвечает на нужные select без сети."""

    is_configured = True
    user_id = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: tuple[str, bool] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"table": table, "filters": dict(filters or {})})
        if table == "vetmo_patches":
            return [{
                "id": 190, "version": "7.39",
                "release_date": "2026-10-01", "is_current": True,
            }]
        if table == "vetmo_heroes":
            return [
                {
                    "id": 42, "name": "wraith_king",
                    "localized_name": "Wraith King", "icon_url": "",
                    "primary_attr": "str", "attack_type": "Melee",
                    "roles": ["Carry", "Support"],
                },
                {
                    "id": 5, "name": "crystal_maiden",
                    "localized_name": "Crystal Maiden", "icon_url": "",
                    "primary_attr": "int", "attack_type": "Ranged",
                    "roles": ["Support"],
                },
            ]
        if table == "vetmo_meta":
            filters = filters or {}
            if filters.get("rank_tier") == 8:
                return [
                    {"hero_id": 42, "position": 1, "pick_share": 2.0,
                     "win_rate": 52.0, "match_count": 100},
                    {"hero_id": 42, "position": 3, "pick_share": 0.5,
                     "win_rate": 51.0, "match_count": 40},
                    {"hero_id": 5, "position": 5, "pick_share": 3.0,
                     "win_rate": 51.5, "match_count": 200},
                ]
            return [
                {"hero_id": 42, "position": 0, "rank_tier": 0,
                 "win_rate": 54.9, "pick_rate": 12.7, "ban_rate": 1.0,
                 "pick_share": 0.0, "match_count": 544563,
                 "delta_win": 0.1, "delta_pick": 0.0, "delta_ban": 0.0,
                 "is_popular": True, "ban_scope": "ALL"},
                {"hero_id": 5, "position": 0, "rank_tier": 0,
                 "win_rate": 51.9, "pick_rate": 14.2, "ban_rate": 1.0,
                 "pick_share": 0.0, "match_count": 608272,
                 "delta_win": 0.1, "delta_pick": 0.0, "delta_ban": 0.0,
                 "is_popular": True, "ban_scope": "ALL"},
            ]
        return []


class _Settings:
    """Минимальный Settings: сервису нужен только размер окна."""

    meta_window_days = 7


def _meta_service() -> tuple[SupabaseMetaService, _StubGateway]:
    gateway = _StubGateway()
    return SupabaseMetaService(gateway, _Settings()), gateway  # type: ignore[arg-type]


def test_rank_zero_rows_get_positions_from_reference_bracket() -> None:
    """Строки «все ранги» получают реальные позиции из среза Immortal."""
    service, _ = _meta_service()

    rows = {row.hero_id: row for row in service.get_meta_rows(
        rank_tier=0, limit=200)}

    assert rows[42].positions == [1, 3]
    assert rows[5].positions == [5]
    assert rows[42].position_stats[1] == PositionStat(
        position=1, pick_share=2.0, win_rate=52.0, match_count=100,
    )


def test_positions_index_is_cached_per_patch() -> None:
    """Индекс позиций запрашивается один раз и живёт в кэше сервиса."""
    service, gateway = _meta_service()

    service._positions_index(190)
    service._positions_index(190)

    index_calls = [
        call for call in gateway.calls
        if call["table"] == "vetmo_meta"
        and call["filters"].get("rank_tier") == 8
    ]
    assert len(index_calls) == 1


class _HeroesStub:
    def __init__(self, heroes: list[Hero]) -> None:
        self._heroes = heroes

    def get_all(self) -> list[Hero]:
        return list(self._heroes)


class _SettingsStub:
    def get_position_priorities(self) -> dict[int, list[int]]:
        return {}


class _MetaStub:
    def __init__(self, rows: list[MetaRow]) -> None:
        self._rows = rows

    def get_meta_map(self) -> dict[int, MetaRow]:
        return {row.hero_id: row for row in self._rows}

    def get_matchups_bulk(
        self, hero_ids: list[int], vs_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        return {}


def _hero(hero_id: int, name: str, roles: list[str]) -> Hero:
    return Hero(
        id=hero_id, name=name, localized_name=name,
        primary_attr="str", attack_type="Melee", roles=roles,
        icon_url=None, is_validated=True,
    )


def _meta_row(hero: Hero, positions: list[int], win_rate: float) -> MetaRow:
    return MetaRow(
        hero_id=hero.id, name=hero.localized_name, hero=hero,
        win_rate=win_rate, pick_rate=10.0, positions=positions,
    )


@pytest.fixture()
def rec_service(tmp_path, monkeypatch) -> SupabaseDraftService:
    """Сервис рекомендаций на двойниках (без сети и без БД)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    wraith = _hero(42, "Wraith King", ["Carry", "Support"])
    maiden = _hero(5, "Crystal Maiden", ["Support"])
    od = _hero(76, "Outworld Devourer", ["Carry"])
    return SupabaseDraftService(
        _StubGateway(),  # type: ignore[arg-type]
        _HeroesStub([wraith, maiden, od]),  # type: ignore[arg-type]
        _SettingsStub(),  # type: ignore[arg-type]
        _MetaStub([  # type: ignore[arg-type]
            _meta_row(wraith, [1, 3], 54.9),
            _meta_row(maiden, [5], 51.9),
            _meta_row(od, [2], 53.2),
        ]),
    )


def test_recommendations_pos5_skip_carry_heroes(rec_service) -> None:
    """На позицию 5 не попадают герои, которые её не играют."""
    ids = [hero.id for hero, _ in rec_service.get_recommendations_for(
        None, 5, limit=10)]

    assert ids == [5]  # Crystal Maiden; Wraith King и OD отфильтрованы


def test_recommendations_pos1_skip_offlane_mid(rec_service) -> None:
    """На позицию 1 остаётся только герой с позицией 1 в мете."""
    ids = [hero.id for hero, _ in rec_service.get_recommendations_for(
        None, 1, limit=10)]

    assert ids == [42]
