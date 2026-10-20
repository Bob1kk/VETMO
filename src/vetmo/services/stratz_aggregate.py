"""Агрегация сырых ответов STRATZ в строки Supabase.

Никаких предположений о «сегодня»: окно — последние 7 доступных дней из
ответа winDay. Дельты — разница с предыдущими 7 доступными днями.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vetmo.domain.models import Hero
from vetmo.domain.rank_brackets import BASIC_BRACKET_BY_RANK


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _round2(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _day_date(day: int) -> str:
    """winDay отдаёт unix-секунды — конвертируем в дату."""
    return datetime.fromtimestamp(int(day), UTC).date().isoformat()


def _day_index(value: object) -> int | None:
    """Нормализует ``day`` STRATZ к индексу дня.

    ``winDay`` возвращает unix-секунды, ``banDay`` — индекс дня.
    """
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number // 86400 if number > 100_000 else number


def _ban_day_date(day: int) -> str:
    """banDay отдаёт индекс дня — конвертируем в ISO-дату."""
    return datetime.fromtimestamp(int(day) * 86400, UTC).date().isoformat()


# В Ranked All Pick каждая команда банит 5 героев -> 10 банов на матч.
BANS_PER_MATCH = 10

# Матчапы: STRATZ отдаёт выборку, поэтому «надёжно» — отдельный порог.
# Строки с меньшей выборкой сохраняем только как fallback, когда надёжных
# матчапов не хватает до десяти.
MATCHUP_RELIABLE_MIN = 500
MATCHUP_MIN_MATCHES = 1
MATCHUP_HIGHLIGHTS_LIMIT = 10


def ban_scope_for_rank(rank: int) -> str | None:
    """Подпись среза банов для rank_tier (0 = все ранги)."""
    if int(rank) == 0:
        return "ALL"
    return BASIC_BRACKET_BY_RANK.get(int(rank))


def window_totals(
    rows: list[dict[str, Any]], *, window_days: int = 7,
) -> dict[int, int]:
    """Сумма матчей героя за последние N доступных дней (для доли позиции)."""
    days = sorted({int(_num(r.get("day"))) for r in rows if r.get("day") is not None})
    current = set(days[-window_days:])
    totals: dict[int, int] = defaultdict(int)
    for row in rows:
        try:
            hero_id = int(row["heroId"])
            day = int(row["day"])
        except (KeyError, TypeError, ValueError):
            continue
        if day in current:
            totals[hero_id] += int(_num(row.get("matchCount")))
    return dict(totals)


def aggregate_win_day(
    rows: list[dict[str, Any]],
    *,
    patch_id: int,
    rank_tier: int,
    position: int,
    window_days: int = 7,
    # Порог минимальной выборки для надёжной метрики (отделен от флага популярности).
    min_matches_for_display: int = 50,
    # Флаг «популярный на позиции» — маркетинговая метка, не влияет на включение в результат.
    min_popular_share: float = 25.0,
    min_popular_matches: int = 500,
    hero_totals: dict[int, int] | None = None,
    # Бан-статистика не зависит от позиции: hero_id -> ban_rate (%).
    ban_rates: dict[int, float] | None = None,
    ban_deltas: dict[int, float] | None = None,
    ban_scope: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Строки vetmo_meta + дата снимка (последний доступный день).

    Семантика matchCount STRATZ (верified по live-интроспекции, см.
    docs/stratz-actual-schema-notes.md):
      - position == 0 (все позиции): в матче 10 герой-слотов ->
        total_matches = sum(matchCount) / 10
      - position > 0: на матче 1 герой на позицию ->
        total_matches = sum(matchCount) / 1
    """
    if not rows:
        return [], None
    by_hero: dict[int, list[dict[str, Any]]] = defaultdict(list)
    days: set[int] = set()
    for row in rows:
        try:
            hero_id = int(row["heroId"])
            day = int(row["day"])
        except (KeyError, TypeError, ValueError):
            continue
        by_hero[hero_id].append(row)
        days.add(day)
    if not days:
        return [], None
    ordered_days = sorted(days)
    current_days = set(ordered_days[-window_days:])
    previous_days = set(ordered_days[-2 * window_days : -window_days])
    snapshot_date = _day_date(ordered_days[-1])

    current_matches: dict[int, int] = {}
    previous_matches: dict[int, int] = {}
    current_wins: dict[int, int] = {}
    previous_wins: dict[int, int] = {}
    for hero_id, hero_rows in by_hero.items():
        current_matches[hero_id] = sum(
            int(_num(r.get("matchCount")))
            for r in hero_rows if int(_num(r.get("day"))) in current_days
        )
        previous_matches[hero_id] = sum(
            int(_num(r.get("matchCount")))
            for r in hero_rows if int(_num(r.get("day"))) in previous_days
        )
        current_wins[hero_id] = sum(
            int(_num(r.get("winCount")))
            for r in hero_rows if int(_num(r.get("day"))) in current_days
        )
        previous_wins[hero_id] = sum(
            int(_num(r.get("winCount")))
            for r in hero_rows if int(_num(r.get("day"))) in previous_days
        )

    # slots_per_match: 10 герой-слотов на матч (все позиции), 1 слот на позицию.
    slots_per_match = 10 if position == 0 else 1
    total_matches = max(1.0, sum(current_matches.values()) / slots_per_match)
    prev_total_matches = max(1.0, sum(previous_matches.values()) / slots_per_match)

    result: list[dict[str, Any]] = []
    for hero_id, matches in current_matches.items():
        # Малая выборка — всё ещё считаем, но помечаем (не скрываем без нужды).
        if matches <= 0:
            continue
        wins = current_wins.get(hero_id, 0)
        win_rate = wins / matches * 100.0
        pick_rate = matches / total_matches * 100.0

        if position > 0:
            total_hero_matches = int((hero_totals or {}).get(hero_id, 0))
            pick_share = (
                matches / total_hero_matches * 100.0
                if total_hero_matches > 0 else None
            )
        else:
            pick_share = None

        prev_matches = previous_matches.get(hero_id, 0)
        prev_wins = previous_wins.get(hero_id, 0)
        delta_win = None
        delta_pick = None
        if prev_matches > 0:
            prev_wr = prev_wins / prev_matches * 100.0
            prev_pick = prev_matches / prev_total_matches * 100.0
            delta_win = _round2(win_rate - prev_wr)
            delta_pick = _round2(pick_rate - prev_pick)

        # is_popular — только маркетинговый флаг, не критерий валидности.
        is_popular = (
            position > 0
            and (pick_share or 0.0) >= min_popular_share
            and matches >= min_popular_matches
        )
        # sample_reliable — метрика считается надёжной для отображения.
        sample_reliable = matches >= min_matches_for_display

        # Баны не зависят от позиции: одно значение на героя в срезе ранга.
        # Если для ранга баны есть, отсутствие героя в выборке = 0 банов.
        ban_rate = None if ban_rates is None else ban_rates.get(hero_id, 0.0)
        delta_ban = None
        if ban_rate is not None and ban_deltas:
            previous_ban = ban_deltas.get(hero_id)
            if previous_ban is not None:
                delta_ban = _round2(ban_rate - previous_ban)

        result.append({
            "patch_id": int(patch_id),
            "hero_id": int(hero_id),
            "rank_tier": int(rank_tier),
            "position": int(position),
            "game_mode": "ALL_PICK_RANKED",
            "window_days": int(window_days),
            "match_count": int(matches),
            "win_count": int(wins),
            "win_rate": round(win_rate, 2),
            "pick_rate": round(pick_rate, 2),
            "ban_rate": _round2(ban_rate),
            "pick_share": _round2(pick_share),
            "is_popular": bool(is_popular),
            "sample_reliable": bool(sample_reliable),
            "delta_win": delta_win,
            "delta_pick": delta_pick,
            "delta_ban": delta_ban,
            "ban_scope": ban_scope,
            "source": "stratz",
        })
    return result, snapshot_date


def snapshot_rows(
    meta_rows: list[dict[str, Any]], snapshot_date: str,
) -> list[dict[str, Any]]:
    """Строки vetmo_snapshots из уже агрегированной меты."""
    result = []
    for row in meta_rows:
        copied = dict(row)
        copied["snapshot_date"] = snapshot_date
        result.append(copied)
    return result


def patch_rows(
    versions: list[dict[str, Any]], *, current_id: int | None, limit: int = 40,
) -> list[dict[str, Any]]:
    """Последние патчи STRATZ -> vetmo_patches (id = gameVersionId)."""
    rows: list[dict[str, Any]] = []
    for item in sorted(
        (v for v in versions if v.get("id") is not None and v.get("name")),
        key=lambda v: int(v["id"]),
        reverse=True,
    )[:limit]:
        patch_id = int(item["id"])
        rows.append({
            "id": patch_id,
            "game_version_id": patch_id,
            "version": str(item["name"]),
            "release_date": None,
            "is_current": patch_id == current_id,
            "source": "stratz",
        })
    return rows


def hero_rows(heroes: list[Hero]) -> list[dict[str, Any]]:
    """Каталог героев для upsert (127 строк)."""
    return [
        {
            "id": hero.id,
            "name": hero.name,
            "localized_name": hero.localized_name,
            "primary_attr": hero.primary_attr,
            "attack_type": hero.attack_type,
            "roles": list(hero.roles),
            "icon_url": hero.icon_url,
            "is_validated": True,
        }
        for hero in heroes
    ]


@dataclass(frozen=True)
class _MatchupCandidate:
    """Один матчап после нормализации STRATZ-строки."""

    other_hero_id: int
    win_rate: float
    match_count: int
    sample_reliable: bool


def _matchup_candidate(
    hero_id: int,
    row: dict[str, Any],
    *,
    min_matches: int,
    reliable_min: int,
) -> _MatchupCandidate | None:
    try:
        other_id = int(row["heroId2"])
        matches = int(_num(row.get("matchCount")))
        wins = int(_num(row.get("winCount")))
    except (KeyError, TypeError, ValueError):
        return None
    if other_id <= 0 or other_id == int(hero_id) or matches < min_matches:
        return None
    return _MatchupCandidate(
        other_hero_id=other_id,
        win_rate=round(wins / matches * 100.0, 2),
        match_count=matches,
        sample_reliable=matches >= reliable_min,
    )


def _candidate_row(
    hero_id: int,
    candidate: _MatchupCandidate,
    *,
    patch_id: int,
    kind: str,
    rank_bracket: str,
    bucket: str | None,
    bucket_rank: int | None,
) -> dict[str, Any]:
    """Строка vetmo_hero_matchups для upsert."""
    return {
        "patch_id": int(patch_id),
        "hero_id": int(hero_id),
        "vs_hero_id": int(candidate.other_hero_id),
        "kind": str(kind),
        "rank_bracket": str(rank_bracket),
        "bucket": bucket,
        "bucket_rank": bucket_rank,
        "win_rate": candidate.win_rate,
        "match_count": int(candidate.match_count),
        "sample_reliable": bool(candidate.sample_reliable),
        "source": "stratz",
        "updated_at": datetime.now(UTC).isoformat(),
    }


def matchup_rows(
    hero_id: int,
    rows: list[dict[str, Any]],
    *,
    patch_id: int,
    kind: str = "vs",
    rank_bracket: str = "ALL",
    min_matches: int = MATCHUP_MIN_MATCHES,
    reliable_min: int = MATCHUP_RELIABLE_MIN,
    bucket: str | None = None,
    bucket_rank: int | None = None,
) -> list[dict[str, Any]]:
    """Строки vetmo_hero_matchups (win_rate героя против оппонента/с союзником)."""
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        candidate = _matchup_candidate(
            hero_id, row, min_matches=min_matches, reliable_min=reliable_min,
        )
        if candidate is None or candidate.other_hero_id in seen:
            continue
        seen.add(candidate.other_hero_id)
        result.append(_candidate_row(
            hero_id, candidate, patch_id=patch_id, kind=kind,
            rank_bracket=rank_bracket, bucket=bucket, bucket_rank=bucket_rank,
        ))
    return result


def select_matchup_highlights(
    hero_id: int,
    rows: list[dict[str, Any]],
    *,
    kind: str,
    limit: int = MATCHUP_HIGHLIGHTS_LIMIT,
    min_matches: int = MATCHUP_MIN_MATCHES,
    reliable_min: int = MATCHUP_RELIABLE_MIN,
    exclude_ids: set[int] | None = None,
) -> list[_MatchupCandidate]:
    """Топ-10 матчапов: сначала надёжные, малая выборка — только fallback.

    ``kind``:
    - ``counter`` — худшие винрейты героя против оппонентов;
    - ``good`` — лучшие винрейты против оппонентов;
    - ``synergy`` — лучшие винрейты в одной команде.
    """
    if kind not in {"counter", "good", "synergy"}:
        raise ValueError(f"Неизвестный вид матчапа: {kind}")
    prepared: list[_MatchupCandidate] = []
    seen: set[int] = set()
    excluded = {int(value) for value in (exclude_ids or set())}
    for row in rows:
        candidate = _matchup_candidate(
            hero_id, row, min_matches=min_matches, reliable_min=reliable_min,
        )
        if (
            candidate is None
            or candidate.other_hero_id in seen
            or candidate.other_hero_id in excluded
        ):
            continue
        seen.add(candidate.other_hero_id)
        prepared.append(candidate)

    reliable = [row for row in prepared if row.sample_reliable]
    low_sample = [row for row in prepared if not row.sample_reliable]
    lowest_first = kind == "counter"

    if lowest_first:
        reliable.sort(key=lambda row: (row.win_rate, -row.match_count))
    else:
        reliable.sort(key=lambda row: (row.win_rate, row.match_count), reverse=True)

    selected = reliable[: max(0, limit)]
    if len(selected) < limit:
        # «Малая выборка» добавляется только если надёжных строк не хватает.
        # Сначала берём самые крупные выборки, а не самые экстремальные WR.
        if lowest_first:
            low_sample.sort(key=lambda row: (row.match_count, -row.win_rate), reverse=True)
        else:
            low_sample.sort(key=lambda row: (row.match_count, row.win_rate), reverse=True)
        selected.extend(low_sample[: limit - len(selected)])
    return selected


def _highlight_rows(
    hero_id: int,
    candidates: list[_MatchupCandidate],
    *,
    patch_id: int,
    kind: str,
    rank_bracket: str,
    bucket: str,
) -> list[dict[str, Any]]:
    return [
        _candidate_row(
            hero_id, candidate, patch_id=patch_id, kind=kind,
            rank_bracket=rank_bracket, bucket=bucket, bucket_rank=index,
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def matchup_bracket_rows(
    hero_id: int,
    groups: dict[str, list[dict[str, Any]]],
    *,
    patch_id: int,
    rank_bracket: str,
    include_full_vs: bool,
    limit: int = MATCHUP_HIGHLIGHTS_LIMIT,
) -> list[dict[str, Any]]:
    """Строки одного среза: полный ``vs`` (для тултипа) + 10 highlights.

    Для ``ALL`` полный список ``vs`` хранится целиком, а highlights
    помечаются в тех же строках через ``bucket``/``bucket_rank``. Для
    ранговых групп хранятся только 10+10+10 highlights, чтобы не раздувать
    таблицу в пять раз.
    """
    vs_rows = groups.get("vs") or []
    with_rows = groups.get("with") or []
    counters = select_matchup_highlights(hero_id, vs_rows, kind="counter", limit=limit)
    good = select_matchup_highlights(
        hero_id, vs_rows, kind="good", limit=limit,
        exclude_ids={row.other_hero_id for row in counters},
    )
    synergies = select_matchup_highlights(hero_id, with_rows, kind="synergy", limit=limit)

    if include_full_vs:
        selected: dict[int, tuple[str, int]] = {}
        for index, candidate in enumerate(counters, start=1):
            selected[candidate.other_hero_id] = ("counter", index)
        for index, candidate in enumerate(good, start=1):
            selected.setdefault(candidate.other_hero_id, ("good", index))
        result = matchup_rows(
            hero_id, vs_rows, patch_id=patch_id,
            kind="vs", rank_bracket=rank_bracket,
        )
        for row in result:
            bucket, bucket_rank = selected.get(
                int(row["vs_hero_id"]), (None, None))
            row["bucket"] = bucket
            row["bucket_rank"] = bucket_rank
        result.extend(_highlight_rows(
            hero_id, synergies, patch_id=patch_id, kind="with",
            rank_bracket=rank_bracket, bucket="synergy",
        ))
        return result

    result = _highlight_rows(
        hero_id, counters, patch_id=patch_id, kind="vs",
        rank_bracket=rank_bracket, bucket="counter",
    )
    result.extend(_highlight_rows(
        hero_id, good, patch_id=patch_id, kind="vs",
        rank_bracket=rank_bracket, bucket="good",
    ))
    result.extend(_highlight_rows(
        hero_id, synergies, patch_id=patch_id, kind="with",
        rank_bracket=rank_bracket, bucket="synergy",
    ))
    return result


def _ban_days(
    rows: list[dict[str, Any]], *, window_days: int, end_day: int | None,
) -> tuple[set[int], set[int]]:
    """Возвращает (текущие, предыдущие) дни окна banDay."""
    days = sorted({
        day for day in (_day_index(row.get("day")) for row in rows)
        if day is not None
    })
    if end_day is not None:
        eligible = [day for day in days if day <= end_day]
        if eligible:
            days = eligible
    if not days:
        return set(), set()
    return (
        set(days[-window_days:]),
        set(days[-2 * window_days:-window_days]),
    )


def _bans_by_bracket(
    rows: list[dict[str, Any]], days: set[int],
) -> dict[str, dict[int, int]]:
    """bracket -> hero_id -> число банов за выбранные дни."""
    grouped: dict[str, dict[int, int]] = {}
    for row in rows:
        day = _day_index(row.get("day"))
        if day is None or day not in days:
            continue
        try:
            hero_id = int(row["heroId"])
            bans = int(_num(row.get("matchCount")))
        except (KeyError, TypeError, ValueError):
            continue
        if bans <= 0:
            continue
        bracket = str(row.get("bracketBasicIds") or "UNKNOWN")
        bucket = grouped.setdefault(bracket, {})
        bucket[hero_id] = bucket.get(hero_id, 0) + bans
    return grouped


def _rates_from_bans(
    grouped: dict[str, dict[int, int]], *, rankings: list[str],
    bans_per_match: int,
) -> dict[int, float]:
    """Доля матчей, где герой забанен, нормированная на 10 банов/матч."""
    totals: dict[int, int] = {}
    for bracket in rankings:
        for hero_id, bans in grouped.get(bracket, {}).items():
            totals[hero_id] = totals.get(hero_id, 0) + bans
    total_bans = sum(totals.values())
    if total_bans <= 0:
        return {}
    sample_matches = total_bans / float(bans_per_match)
    return {
        hero_id: min(100.0, round(bans / sample_matches * 100.0, 2))
        for hero_id, bans in totals.items()
    }


def ban_rates_by_rank(
    rows: list[dict[str, Any]],
    *,
    window_days: int = 7,
    end_day: int | None = None,
    bans_per_match: int = BANS_PER_MATCH,
) -> tuple[dict[int, dict[int, float]], dict[int, dict[int, float]]]:
    """banDay -> (текущие, предыдущие) ban_rate по рангам.

    Результат: ``rank_tier -> hero_id -> ban_rate (%)``. Ранг 0 — все
    ранги (сумма групп), ранги 1..8 — соответствующая группа STRATZ.
    """
    current_days, previous_days = _ban_days(
        rows, window_days=window_days, end_day=end_day,
    )
    if not current_days:
        return {}, {}
    current_bans = _bans_by_bracket(rows, current_days)
    previous_bans = _bans_by_bracket(rows, previous_days)
    all_brackets = list(current_bans)

    current: dict[int, dict[int, float]] = {}
    previous: dict[int, dict[int, float]] = {}
    for rank in range(0, 9):
        rankings = (
            all_brackets if rank == 0
            else (
                [BASIC_BRACKET_BY_RANK[rank]]
                if rank in BASIC_BRACKET_BY_RANK else []
            )
        )
        rates = _rates_from_bans(
            current_bans, rankings=rankings, bans_per_match=bans_per_match,
        )
        if rates:
            current[rank] = rates
        previous_rates = _rates_from_bans(
            previous_bans, rankings=rankings, bans_per_match=bans_per_match,
        )
        if previous_rates:
            previous[rank] = previous_rates
    return current, previous


def ban_stats_rows(
    rows: list[dict[str, Any]],
    *,
    patch_id: int,
    window_days: int = 7,
    end_day: int | None = None,
    bans_per_match: int = BANS_PER_MATCH,
) -> list[dict[str, Any]]:
    """Диагностика banDay: баны по дням и ранговым группам.

    ``total_matches`` — оценка покрытых матчей (``total_bans / 10``),
    поэтому ``ban_rate`` здесь не заполняется: осмысленен только
    пер-геройный банрейт из :func:`ban_rates_by_rank`.
    """
    current_days, _ = _ban_days(
        rows, window_days=window_days, end_day=end_day,
    )
    grouped: dict[tuple[int, str], int] = {}
    for row in rows:
        day = _day_index(row.get("day"))
        if day is None or day not in current_days:
            continue
        bracket = str(row.get("bracketBasicIds") or "UNKNOWN")
        bans = int(_num(row.get("matchCount")))
        if bans <= 0:
            continue
        grouped[(day, bracket)] = grouped.get((day, bracket), 0) + bans

    result: list[dict[str, Any]] = []
    for (day, bracket), total_bans in sorted(grouped.items()):
        result.append({
            "snapshot_date": _ban_day_date(day),
            "patch_id": int(patch_id),
            "rank_tier": 0,
            "bracket": bracket,
            "total_bans": int(total_bans),
            "total_matches": int(round(total_bans / float(bans_per_match))),
            "ban_rate": None,
            "source": "stratz",
        })
    return result


__all__ = [
    "MATCHUP_HIGHLIGHTS_LIMIT",
    "MATCHUP_MIN_MATCHES",
    "MATCHUP_RELIABLE_MIN",
    "aggregate_win_day",
    "ban_rates_by_rank",
    "ban_scope_for_rank",
    "ban_stats_rows",
    "hero_rows",
    "matchup_bracket_rows",
    "matchup_rows",
    "patch_rows",
    "select_matchup_highlights",
    "snapshot_rows",
]
