"""Тесты матчапов: топ-10, надёжность выборки и отсутствие дублей."""

from __future__ import annotations

from vetmo.services.stratz_aggregate import (
    matchup_bracket_rows,
    matchup_rows,
    select_matchup_highlights,
)


def _row(other_id: int, matches: int, wins: int) -> dict[str, int]:
    return {
        "heroId2": other_id,
        "matchCount": matches,
        "winCount": wins,
    }


def test_matchup_rows_store_reliability_and_extended_fields() -> None:
    rows = matchup_rows(
        42,
        [_row(82, 1000, 460), _row(12, 400, 200), _row(42, 1000, 500)],
        patch_id=7,
        rank_bracket="ALL",
    )

    assert len(rows) == 2  # сам герой исключён; 400 матчей — просто low sample
    by_id = {row["vs_hero_id"]: row for row in rows}
    assert by_id[82]["sample_reliable"] is True
    assert by_id[12]["sample_reliable"] is False
    assert by_id[82]["kind"] == "vs"
    assert by_id[82]["rank_bracket"] == "ALL"
    assert by_id[82]["win_rate"] == 46.0


def test_select_highlights_prefers_reliable_rows() -> None:
    rows = [
        _row(100 + index, 1000, int(1000 * rate))
        for index, rate in enumerate((0.40, 0.42, 0.44, 0.46, 0.48))
    ]
    rows += [_row(200 + index, 100, 100 - index) for index in range(8)]

    selected = select_matchup_highlights(42, rows, kind="counter", limit=10)

    assert len(selected) == 10
    assert all(item.sample_reliable for item in selected[:5])
    assert all(not item.sample_reliable for item in selected[5:])
    # Первые пять — худшие надёжные WR по возрастанию.
    assert [item.win_rate for item in selected[:5]] == [40.0, 42.0, 44.0, 46.0, 48.0]


def test_select_highlights_counter_good_no_overlap() -> None:
    rows = [
        _row(100 + index, 1000, int(1000 * rate / 100))
        for index, rate in enumerate(range(40, 60))
    ]
    counters = select_matchup_highlights(42, rows, kind="counter", limit=10)
    good = select_matchup_highlights(
        42, rows, kind="good", limit=10,
        exclude_ids={row.other_hero_id for row in counters},
    )

    assert len(counters) == 10
    assert len(good) == 10
    # Контрпики и хорошие пики не пересекаются: разные концы распределения WR.
    assert not ({item.other_hero_id for item in counters}
                & {item.other_hero_id for item in good})
    assert counters[0].win_rate == 40.0
    assert good[0].win_rate == 59.0


def test_matchup_bracket_rows_all_marks_highlights_without_duplicate_pk() -> None:
    vs_rows = [
        _row(100 + index, 1000, int(1000 * rate / 100))
        for index, rate in enumerate(range(40, 60))
    ]
    with_rows = [
        _row(300 + index, 1000, int(1000 * rate / 100))
        for index, rate in enumerate(range(55, 75))
    ]

    rows = matchup_bracket_rows(
        42,
        {"vs": vs_rows, "with": with_rows},
        patch_id=7,
        rank_bracket="ALL",
        include_full_vs=True,
    )

    buckets = {"counter": 0, "good": 0, "synergy": 0}
    for row in rows:
        if row["bucket"] is not None:
            buckets[row["bucket"]] += 1
    assert buckets == {"counter": 10, "good": 10, "synergy": 10}
    assert len(rows) == len({(row["kind"], row["vs_hero_id"]) for row in rows})


def test_matchup_bracket_rows_rank_slice_stores_only_highlights() -> None:
    vs_rows = [
        _row(100 + index, 1000, int(1000 * rate / 100))
        for index, rate in enumerate(range(40, 60))
    ]
    with_rows = [
        _row(300 + index, 1000, int(1000 * rate / 100))
        for index, rate in enumerate(range(55, 75))
    ]

    rows = matchup_bracket_rows(
        42,
        {"vs": vs_rows, "with": with_rows},
        patch_id=7,
        rank_bracket="CRUSADER_ARCHON",
        include_full_vs=False,
    )

    assert len(rows) == 30
    assert all(row["bucket"] is not None for row in rows)
    assert len({(row["kind"], row["vs_hero_id"]) for row in rows}) == 30
