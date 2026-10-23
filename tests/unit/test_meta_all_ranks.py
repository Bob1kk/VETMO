"""Агрегация среза «Все ранги + позиция» (rank_tier=0 в БД отсутствует).

В ``vetmo_meta`` нет per-position строк для rank_tier=0, поэтому UI собирает
срез из строк рангов 1..8, взвешивая метрики по match_count.
"""

from __future__ import annotations

from vetmo.services.supabase_meta import _aggregate_all_ranks, _group_rows


def test_aggregate_all_ranks_weights_by_match_count() -> None:
    """WR/пики/дельты — взвешенные средние, матчи — сумма по рангам."""
    rows = [
        {
            "hero_id": 1, "position": 3, "rank_tier": 1,
            "win_rate": 50.0, "pick_rate": 2.0, "match_count": 100,
            "delta_win": 1.0, "ban_scope": "HERALD",
        },
        {
            "hero_id": 1, "position": 3, "rank_tier": 2,
            "win_rate": 54.0, "pick_rate": 4.0, "match_count": 300,
            "delta_win": 3.0, "ban_scope": "GUARDIAN",
        },
        {
            "hero_id": 2, "position": 3, "rank_tier": 1,
            "win_rate": 52.0, "pick_rate": 1.0, "match_count": 50,
        },
    ]

    result = {
        row["hero_id"]: row
        for row in _aggregate_all_ranks(_group_rows(rows), 3)
    }

    hero1 = result[1]
    assert hero1["win_rate"] == 53.0  # (50*100 + 54*300) / 400
    assert hero1["pick_rate"] == 3.5  # (2*100 + 4*300) / 400
    assert hero1["delta_win"] == 2.5
    assert hero1["match_count"] == 400
    assert hero1["positions"] == [3]
    assert hero1["position_details"][3]["win_rate"] == 53.0
    assert hero1["ban_scope"] == "GUARDIAN"  # из самого крупного среза

    assert result[2]["match_count"] == 50


def test_aggregate_all_ranks_skips_heroes_without_position() -> None:
    """Герой, популярный только на других позициях, в срез не попадает."""
    rows = [
        {"hero_id": 5, "position": 1, "rank_tier": 4, "win_rate": 55.0,
         "match_count": 10},
        {"hero_id": 6, "position": 3, "rank_tier": 4, "win_rate": 49.0,
         "match_count": 10},
    ]

    result = _aggregate_all_ranks(_group_rows(rows), 3)

    assert [row["hero_id"] for row in result] == [6]
