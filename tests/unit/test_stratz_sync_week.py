"""Тесты недельного окна STRATZ (stats/matchUp принимают unix-время)."""

from __future__ import annotations

from datetime import UTC, datetime

from vetmo.services.stratz_sync import _week_end_date, _week_start_timestamp

WEEK_START_15_OCT = 1792022400


def test_week_start_is_thursday() -> None:
    wednesday = datetime(2026, 10, 21, 15, 30, tzinfo=UTC)
    assert _week_start_timestamp(wednesday) == WEEK_START_15_OCT

    thursday = datetime(2026, 10, 15, 0, 5, tzinfo=UTC)
    assert _week_start_timestamp(thursday) == WEEK_START_15_OCT

    monday = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    assert _week_start_timestamp(monday) == WEEK_START_15_OCT


def test_week_end_is_wednesday() -> None:
    assert _week_end_date(WEEK_START_15_OCT) == "2026-10-21"
    assert _week_end_date(WEEK_START_15_OCT - 7 * 86400) == "2026-10-14"
