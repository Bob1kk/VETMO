"""Тесты агрегации STRATZ: режим Ranked All Pick и банрейт из banDay."""

from __future__ import annotations

import pytest

from vetmo.services.stratz_aggregate import (
    _day_index,
    aggregate_hero_stats_week,
    aggregate_win_day,
    ban_rates_by_rank,
)


def _ban(
    hero_id: int,
    day: int,
    bracket: str,
    bans: int,
) -> dict[str, object]:
    return {
        "heroId": hero_id,
        "day": day,
        "bracketBasicIds": bracket,
        "matchCount": bans,
        "winCount": bans // 2,
    }


def _bracket_rows(
    day: int, bracket: str, hero42: int, hero76: int,
) -> list[dict[str, object]]:
    """10 матчей = 100 банов: 2 целевых героя + добивка до 100."""
    rows = [_ban(42, day, bracket, hero42), _ban(76, day, bracket, hero76)]
    remaining = 100 - hero42 - hero76
    for index, hero_id in enumerate(range(101, 111)):
        share = remaining // 10 + (1 if index < remaining % 10 else 0)
        if share:
            rows.append(_ban(hero_id, day, bracket, share))
    return rows


def test_day_index_handles_seconds_and_day_numbers() -> None:
    assert _day_index(1791590400) == 20736
    assert _day_index(20736) == 20736
    assert _day_index(None) is None


def test_ban_rates_by_rank_normalizes_and_maps_brackets() -> None:
    # 10 матчей на группу -> 100 банов.
    rows = _bracket_rows(100, "DIVINE_IMMORTAL", hero42=2, hero76=8)
    rows += _bracket_rows(100, "HERALD_GUARDIAN", hero42=5, hero76=5)

    current, previous = ban_rates_by_rank(rows, window_days=7)

    # Все ранги: 20 матчей -> 200 банов.
    assert current[0][42] == 35.0
    assert current[0][76] == 65.0
    # Ранги 7 и 8 -> DIVINE_IMMORTAL.
    assert current[7][42] == 20.0
    assert current[7][76] == 80.0
    assert current[8] == current[7]
    # Ранги 1 и 2 -> HERALD_GUARDIAN.
    assert current[1][42] == 50.0
    assert current[1][76] == 50.0
    assert current[2] == current[1]
    # Прошлого окна нет.
    assert previous == {}


def test_ban_rates_compute_delta_window() -> None:
    rows = _bracket_rows(100, "DIVINE_IMMORTAL", hero42=2, hero76=8)
    rows += _bracket_rows(93, "DIVINE_IMMORTAL", hero42=1, hero76=9)

    current, previous = ban_rates_by_rank(rows, window_days=1)

    assert current[7][42] == 20.0
    assert current[7][76] == 80.0
    assert previous[7][42] == 10.0
    assert previous[7][76] == 90.0


def test_aggregate_win_day_uses_ranked_mode_and_ban_fields() -> None:
    win_rows = [
        {
            "heroId": 42,
            "day": 1791590400,  # 2026-10-10
            "matchCount": 1000,
            "winCount": 550,
        },
    ]

    rows, snapshot = aggregate_win_day(
        win_rows,
        patch_id=190,
        rank_tier=0,
        position=0,
        ban_rates={42: 20.0},
        ban_deltas={42: 18.0},
        ban_scope="ALL",
    )

    assert snapshot == "2026-10-10"
    assert len(rows) == 1
    row = rows[0]
    assert row["game_mode"] == "ALL_PICK_RANKED"
    assert row["win_rate"] == pytest.approx(55.0)
    assert row["ban_rate"] == pytest.approx(20.0)
    assert row["delta_ban"] == pytest.approx(2.0)
    assert row["ban_scope"] == "ALL"


def _stats(
    bracket: str,
    position: object,
    hero_id: int,
    matches: int,
    wins: int,
) -> dict[str, object]:
    return {
        "bracketBasicIds": bracket,
        "position": position,
        "heroId": hero_id,
        "matchCount": matches,
        "winCount": wins,
    }


def test_aggregate_hero_stats_week_maps_positions_and_rates() -> None:
    rows = [
        _stats("DIVINE_IMMORTAL", "POSITION_1", 1, 100, 60),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 2, 100, 40),
        _stats("DIVINE_IMMORTAL", "POSITION_2", 1, 50, 30),
        _stats("DIVINE_IMMORTAL", "POSITION_2", 2, 150, 60),
    ]

    result = aggregate_hero_stats_week(
        rows, patch_id=190, ranks=range(8, 9), positions=range(0, 3),
    )

    assert len(result) == 6
    by_key = {(r["rank_tier"], r["position"], r["hero_id"]): r for r in result}

    overall = by_key[(8, 0, 1)]
    assert overall["match_count"] == 150
    assert overall["win_rate"] == pytest.approx(60.0)
    # 400 суммарных матчей героев / 10 слотов = 40 матчей.
    assert overall["pick_rate"] == pytest.approx(375.0)
    assert overall["pick_share"] is None
    assert overall["ban_scope"] == "DIVINE_IMMORTAL"

    position_one = by_key[(8, 1, 1)]
    assert position_one["match_count"] == 100
    assert position_one["win_rate"] == pytest.approx(60.0)
    # Позиционный pick rate нормирован на 100% по всем героям позиции.
    assert position_one["pick_rate"] == pytest.approx(50.0)
    assert position_one["pick_share"] == pytest.approx(66.67)
    assert position_one["sample_reliable"] is True

    position_two = by_key[(8, 2, 2)]
    assert position_two["win_rate"] == pytest.approx(40.0)
    assert position_two["pick_rate"] == pytest.approx(75.0)
    assert position_two["pick_share"] == pytest.approx(60.0)


def test_aggregate_hero_stats_week_rank_zero_sums_all_brackets() -> None:
    rows = [
        _stats("HERALD_GUARDIAN", "POSITION_1", 1, 100, 50),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 1, 100, 70),
        _stats("UNCALIBRATED", "POSITION_1", 1, 50, 20),
    ]

    result = aggregate_hero_stats_week(
        rows, patch_id=190, ranks=range(0, 2), positions=range(1, 2),
    )

    by_key = {(r["rank_tier"], r["position"], r["hero_id"]): r for r in result}
    assert set(by_key) == {(0, 1, 1), (1, 1, 1)}

    overall = by_key[(0, 1, 1)]
    assert overall["match_count"] == 250
    assert overall["win_count"] == 140
    assert overall["win_rate"] == pytest.approx(56.0)
    assert overall["pick_rate"] == pytest.approx(100.0)
    assert overall["ban_scope"] == "ALL"

    herald = by_key[(1, 1, 1)]
    assert herald["match_count"] == 100
    assert herald["win_rate"] == pytest.approx(50.0)
    assert herald["ban_scope"] == "HERALD_GUARDIAN"


def test_aggregate_hero_stats_week_ignores_invalid_rows() -> None:
    rows = [
        _stats("DIVINE_IMMORTAL", "POSITION_0", 1, 100, 60),
        _stats("DIVINE_IMMORTAL", "POSITION_6", 1, 100, 60),
        _stats("DIVINE", "POSITION_1", 1, 100, 60),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 0, 100, 60),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 2, 0, 0),
        {
            "bracketBasicIds": "DIVINE_IMMORTAL",
            "position": "POSITION_1",
            "heroId": 3,
            "matchCount": 100,
            "winCount": 55,
        },
        _stats("DIVINE_IMMORTAL", 2, 4, 200, 100),
    ]

    result = aggregate_hero_stats_week(
        rows, patch_id=190, ranks=range(8, 9), positions=range(0, 3),
    )

    assert [(r["position"], r["hero_id"]) for r in result if r["position"] > 0] == [
        (1, 3),
        (2, 4),
    ]
    assert {r["hero_id"] for r in result} == {3, 4}


def test_aggregate_hero_stats_week_computes_deltas_and_bans() -> None:
    current = [
        _stats("DIVINE_IMMORTAL", "POSITION_1", 1, 200, 120),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 2, 200, 80),
    ]
    previous = [
        _stats("DIVINE_IMMORTAL", "POSITION_1", 1, 150, 75),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 2, 50, 25),
    ]

    result = aggregate_hero_stats_week(
        current,
        patch_id=190,
        ranks=range(8, 9),
        positions=range(1, 2),
        previous_rows=previous,
        ban_rates={8: {1: 20.0}},
        ban_deltas={8: {1: 18.0}},
    )

    by_hero = {r["hero_id"]: r for r in result}
    assert by_hero[1]["delta_win"] == pytest.approx(10.0)
    assert by_hero[1]["delta_pick"] == pytest.approx(-25.0)
    assert by_hero[1]["ban_rate"] == pytest.approx(20.0)
    assert by_hero[1]["delta_ban"] == pytest.approx(2.0)

    assert by_hero[2]["delta_win"] == pytest.approx(-10.0)
    assert by_hero[2]["delta_pick"] == pytest.approx(25.0)
    assert by_hero[2]["ban_rate"] == pytest.approx(0.0)
    assert by_hero[2]["delta_ban"] is None


def test_aggregate_hero_stats_week_popularity_requires_share_and_matches() -> None:
    rows = [
        _stats("DIVINE_IMMORTAL", "POSITION_1", 1, 600, 300),
        _stats("DIVINE_IMMORTAL", "POSITION_1", 2, 400, 200),
        _stats("DIVINE_IMMORTAL", "POSITION_2", 1, 400, 200),
        _stats("DIVINE_IMMORTAL", "POSITION_2", 2, 600, 300),
    ]

    result = aggregate_hero_stats_week(
        rows, patch_id=190, ranks=range(8, 9), positions=range(0, 3),
    )

    by_key = {(r["position"], r["hero_id"]): r for r in result}
    assert by_key[(1, 1)]["pick_share"] == pytest.approx(60.0)
    assert by_key[(1, 1)]["is_popular"] is True
    assert by_key[(1, 2)]["pick_share"] == pytest.approx(40.0)
    assert by_key[(1, 2)]["is_popular"] is False
    assert by_key[(0, 1)]["is_popular"] is False


def test_aggregate_hero_stats_week_empty_rows_returns_empty() -> None:
    assert aggregate_hero_stats_week([], patch_id=190) == []
