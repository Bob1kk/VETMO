"""Дневные тренды OpenDota и скользящее окно 7 дней."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from vetmo.services.stratz_sync import (
    DAILY_WINDOW_DAYS,
    _daily_trend_rows,
    _previous_snapshot_map,
    _rolling_daily_totals,
)


def _record(
    *,
    hero_id: int = 1,
    picks: list[int] | None = None,
    wins: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "id": hero_id,
        "pub_pick_trend": picks if picks is not None else list(range(10, 80, 10)),
        "pub_win_trend": wins if wins is not None else list(range(5, 40, 5)),
    }


def test_daily_trend_rows_map_oldest_to_newest() -> None:
    end_date = date(2026, 10, 23)
    rows = _daily_trend_rows(
        _record(picks=[1, 2, 3, 4, 5, 6, 7], wins=[1, 1, 2, 2, 3, 3, 4]),
        patch_id=190,
        end_date=end_date,
    )

    assert len(rows) == DAILY_WINDOW_DAYS
    assert [row["stat_date"] for row in rows] == [
        (end_date - timedelta(days=6 - index)).isoformat()
        for index in range(7)
    ]
    assert rows[-1]["match_count"] == 7
    assert rows[-1]["win_count"] == 4
    assert rows[0]["rank_tier"] == 0
    assert rows[0]["source"] == "opendota"


def test_daily_trend_rows_use_only_last_seven_buckets() -> None:
    rows = _daily_trend_rows(
        _record(picks=[99, 1, 2, 3, 4, 5, 6, 7], wins=[99, 1, 1, 1, 2, 2, 3, 3]),
        patch_id=190,
        end_date=date(2026, 10, 23),
    )

    assert len(rows) == 7
    assert rows[0]["match_count"] == 1
    assert rows[-1]["match_count"] == 7


def test_daily_trend_rows_require_both_trends() -> None:
    record = _record()
    record["pub_win_trend"] = None

    assert _daily_trend_rows(
        record, patch_id=190, end_date=date(2026, 10, 23),
    ) == []


def test_daily_trend_rows_clamp_wins_to_matches() -> None:
    rows = _daily_trend_rows(
        _record(picks=[10], wins=[12]),
        patch_id=190,
        end_date=date(2026, 10, 23),
    )

    assert rows[0]["win_count"] == 10


def test_rolling_daily_totals_use_last_seven_calendar_days() -> None:
    end_date = date(2026, 10, 23)
    rows = [
        {"stat_date": (end_date - timedelta(days=7)).isoformat(),
         "match_count": 100, "win_count": 50},
        {"stat_date": (end_date - timedelta(days=6)).isoformat(),
         "match_count": 10, "win_count": 6},
        {"stat_date": (end_date - timedelta(days=1)).isoformat(),
         "match_count": 20, "win_count": 9},
        {"stat_date": end_date.isoformat(),
         "match_count": 30, "win_count": 18},
    ]

    matches, wins = _rolling_daily_totals(rows, end_date=end_date)

    assert matches == 60
    assert wins == 33


def test_trend_sum_matches_pub_totals() -> None:
    picks = [110508, 114835, 98258, 97021, 99307, 87850, 59010]
    wins = [56383, 58847, 50067, 49976, 50703, 45340, 30181]
    rows = _daily_trend_rows(
        _record(picks=picks, wins=wins),
        patch_id=190,
        end_date=date(2026, 10, 23),
    )

    assert sum(row["match_count"] for row in rows) == sum(picks)
    assert sum(row["win_count"] for row in rows) == sum(wins)


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def select(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"table": table, **kwargs})
        if len(self.calls) == 1:
            return [{"snapshot_date": "2026-10-22"}]
        return [{"hero_id": 1, "rank_tier": 0,
                 "win_rate": 50.0, "pick_rate": 10.0}]


def test_previous_snapshot_is_yesterday_not_week_ago() -> None:
    gateway = _Gateway()

    previous = _previous_snapshot_map(gateway, 190, date(2026, 10, 23))

    assert previous[(1, 0)]["win_rate"] == 50.0
    assert gateway.calls[0]["filters"]["snapshot_date"] == (
        "lte", "2026-10-22",
    )
