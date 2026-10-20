"""Тесты агрегации STRATZ: режим Ranked All Pick и банрейт из banDay."""

from __future__ import annotations

import pytest

from vetmo.services.stratz_aggregate import (
    _day_index,
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
