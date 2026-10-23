"""Позиции героев для среза rank_tier=0 и фильтр рекомендаций.

В ``vetmo_meta`` нет per-position строк для rank_tier=0, поэтому позиции
героя собираются по всем рангам 1..8: считаем долю игр героя на позиции
(match_count) и оставляем позиции выше порога. Immortal-срез не подходит:
на верхних рангах популярность позиций смещена (Necrophos-carry и т.п.).
"""

from __future__ import annotations

from typing import Any

import pytest

from vetmo.domain.meta_row import MetaRow, PositionStat
from vetmo.domain.models import DraftPick, DraftSession, Hero
from vetmo.services import supabase_meta
from vetmo.services.supabase_draft import SupabaseDraftService
from vetmo.services.supabase_meta import SupabaseMetaService


class _StubGateway:
    """Двойник SupabaseGateway: отвечает на нужные select без сети."""

    is_configured = True
    user_id = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # Две «страницы» per-position строк: проверяем пагинацию и агрегацию.
        self.per_position_rows: list[dict[str, Any]] = [
            {"hero_id": 42, "position": 1, "win_rate": 52.0, "match_count": 100},
            {"hero_id": 42, "position": 3, "win_rate": 51.0, "match_count": 40},
            {"hero_id": 5, "position": 5, "win_rate": 51.5, "match_count": 200},
            {"hero_id": 42, "position": 1, "win_rate": 52.0, "match_count": 100},
            {"hero_id": 42, "position": 3, "win_rate": 51.0, "match_count": 60},
        ]

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: tuple[str, bool] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({
            "table": table, "filters": dict(filters or {}), "offset": offset,
        })
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
            rank = filters.get("rank_tier")
            if isinstance(rank, tuple) and rank[0] == "in":
                start = int(offset or 0)
                size = int(limit or len(self.per_position_rows))
                return self.per_position_rows[start:start + size]
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


def _meta_service(
    tmp_path, monkeypatch,
) -> tuple[SupabaseMetaService, _StubGateway]:
    """Сервис на двойнике; APPDATA изолирован, чтобы не трогать кэш позиций."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    gateway = _StubGateway()
    return SupabaseMetaService(gateway, _Settings()), gateway  # type: ignore[arg-type]


def test_rank_zero_positions_come_from_all_ranks_pick_share(
    tmp_path, monkeypatch,
) -> None:
    """Позиции — по доле игр на позиции, агрегированной по рангам 1..8."""
    service, _ = _meta_service(tmp_path, monkeypatch)

    rows = {row.hero_id: row for row in service.get_meta_rows(
        rank_tier=0, limit=200)}

    # WK: pos 1 = 200 матчей, pos 3 = 100 -> доли 66.7% / 33.3%.
    assert rows[42].positions == [1, 3]
    assert rows[42].position_stats[1] == PositionStat(
        position=1, pick_share=66.7, win_rate=52.0, match_count=200,
    )
    assert rows[5].positions == [5]
    assert rows[5].position_stats[5] == PositionStat(
        position=5, pick_share=100.0, win_rate=51.5, match_count=200,
    )


def test_positions_index_reads_all_pages_and_caches(
    tmp_path, monkeypatch,
) -> None:
    """Индекс читается страницами (PostgREST max 1000) и кэшируется."""
    service, gateway = _meta_service(tmp_path, monkeypatch)
    original = supabase_meta._POSITION_PAGE
    supabase_meta._POSITION_PAGE = 2
    try:
        index = service._positions_index(190)
        service._positions_index(190)
    finally:
        supabase_meta._POSITION_PAGE = original

    assert set(index[42]) == {1, 3}
    offsets = [
        call["offset"] for call in gateway.calls
        if call["table"] == "vetmo_meta"
        and isinstance(call["filters"].get("rank_tier"), tuple)
    ]
    # 5 строк по 2: страницы 0, 2, 4 (последняя неполная -> стоп).
    assert sorted(offsets) == [0, 2, 4]


class _HeroesStub:
    def __init__(self, heroes: list[Hero]) -> None:
        self._heroes = heroes

    def get_all(self) -> list[Hero]:
        return list(self._heroes)


class _MetaStub:
    def __init__(
        self,
        rows: list[MetaRow],
        matchups: dict[int, list[dict[str, Any]]] | None = None,
        synergies: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._rows = rows
        self._matchups = matchups or {}
        self._synergies = synergies or {}

    def get_meta_map(self) -> dict[int, MetaRow]:
        return {row.hero_id: row for row in self._rows}

    def get_matchups_bulk(
        self, hero_ids: list[int], vs_ids: list[int],
        patch_id: int | None = None, kind: str = "vs",
    ) -> dict[int, list[dict[str, Any]]]:
        return self._matchups

    def get_synergies_bulk(
        self, hero_ids: list[int], partner_ids: list[int],
        patch_id: int | None = None,
    ) -> dict[int, list[dict[str, Any]]]:
        return self._synergies


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


def _draft_service(
    tmp_path, monkeypatch, meta: _MetaStub, heroes: list[Hero],
) -> SupabaseDraftService:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return SupabaseDraftService(
        _StubGateway(),  # type: ignore[arg-type]
        _HeroesStub(heroes),  # type: ignore[arg-type]
        meta,  # type: ignore[arg-type]
    )


@pytest.fixture()
def rec_service(tmp_path, monkeypatch) -> SupabaseDraftService:
    """Сервис рекомендаций на двойниках (без сети и без БД)."""
    wraith = _hero(42, "Wraith King", ["Carry", "Support"])
    maiden = _hero(5, "Crystal Maiden", ["Support"])
    od = _hero(76, "Outworld Devourer", ["Carry"])
    return _draft_service(
        tmp_path, monkeypatch,
        _MetaStub([
            _meta_row(wraith, [1, 3], 54.9),
            _meta_row(maiden, [5], 51.9),
            _meta_row(od, [2], 53.2),
        ]),
        [wraith, maiden, od],
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


@pytest.fixture()
def counter_service(tmp_path, monkeypatch) -> SupabaseDraftService:
    """Три керри-героя, один враг и один союзник для контр-пиков/связок."""
    alpha = _hero(1, "Alpha", ["Carry"])
    beta = _hero(2, "Beta", ["Carry"])
    gamma = _hero(3, "Gamma", ["Carry"])
    meta = _MetaStub(
        [
            _meta_row(alpha, [1], 50.0),
            _meta_row(beta, [1], 50.0),
            _meta_row(gamma, [1], 50.0),
        ],
        matchups={
            1: [{"vs_hero_id": 99, "win_rate": 56.0,
                 "match_count": 5000, "sample_reliable": True}],
            2: [{"vs_hero_id": 99, "win_rate": 48.0,
                 "match_count": 5000, "sample_reliable": True}],
            # малая выборка не должна давать контр-пик
            3: [{"vs_hero_id": 99, "win_rate": 70.0,
                 "match_count": 100, "sample_reliable": True}],
        },
        synergies={
            2: [{"vs_hero_id": 98, "win_rate": 60.0,
                 "match_count": 3000, "sample_reliable": True}],
        },
    )
    return _draft_service(
        tmp_path, monkeypatch, meta, [alpha, beta, gamma])


def _state() -> DraftSession:
    """Пик врага (99) и союзника (98); сейчас пикает Radiant."""
    return DraftSession(
        current_step=0,
        picks=[
            DraftPick(team="dire", position=5, hero_id=99, step=0),
            DraftPick(team="radiant", position=5, hero_id=98, step=1),
        ],
    )


def test_details_rank_counters_first_then_synergy(counter_service) -> None:
    """Контр-пик важнее связки: Alpha (контрит врага) — первый."""
    details = counter_service.get_recommendation_details(
        _state(), 1, limit=3, team="radiant")
    by_id = {rec.hero.id: rec for rec in details}

    assert details[0].hero.id == 1
    assert by_id[1].counter == pytest.approx(6.0)
    assert by_id[2].counter == pytest.approx(-2.0)
    assert by_id[2].synergy == pytest.approx(10.0)
    # Малая выборка (100 игр) не считается контр-пиком.
    assert by_id[3].counter == 0.0


def test_recommendations_for_wraps_details(counter_service) -> None:
    """Старый API возвращает те же (Hero, score) без разложения."""
    details = counter_service.get_recommendation_details(
        _state(), 1, limit=3, team="radiant")
    wrapped = counter_service.get_recommendations_for(
        _state(), 1, limit=3, team="radiant")

    assert [hero.id for hero, _ in wrapped] == [
        rec.hero.id for rec in details
    ]
    assert [score for _, score in wrapped] == pytest.approx(
        [rec.score for rec in details])
