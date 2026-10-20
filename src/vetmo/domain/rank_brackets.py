"""Ранговые группы STRATZ для матчапов и банов.

STRATZ отдаёт ``bracketBasicIds`` пятью группами; в UI ранги 1..8
складываются в те же группы, чтобы не выдумывать несуществующие срезы.
"""

from __future__ import annotations

ALL_BRACKET = "ALL"

BASIC_BRACKETS: tuple[str, ...] = (
    "HERALD_GUARDIAN",
    "CRUSADER_ARCHON",
    "LEGEND_ANCIENT",
    "DIVINE_IMMORTAL",
)

BASIC_BRACKET_BY_RANK: dict[int, str] = {
    1: "HERALD_GUARDIAN",
    2: "HERALD_GUARDIAN",
    3: "CRUSADER_ARCHON",
    4: "CRUSADER_ARCHON",
    5: "LEGEND_ANCIENT",
    6: "LEGEND_ANCIENT",
    7: "DIVINE_IMMORTAL",
    8: "DIVINE_IMMORTAL",
}

BASIC_BRACKET_LABELS: dict[str, str] = {
    "ALL": "все ранги",
    "HERALD_GUARDIAN": "Herald–Guardian",
    "CRUSADER_ARCHON": "Crusader–Archon",
    "LEGEND_ANCIENT": "Legend–Ancient",
    "DIVINE_IMMORTAL": "Divine–Immortal",
}


def basic_bracket_for_rank(rank_tier: int) -> str:
    """Ранг 0..8 -> группа STRATZ (0 — все ранги)."""
    try:
        rank = int(rank_tier)
    except (TypeError, ValueError):
        return ALL_BRACKET
    if rank == 0:
        return ALL_BRACKET
    return BASIC_BRACKET_BY_RANK.get(rank, ALL_BRACKET)


def basic_bracket_label(bracket: str | None) -> str:
    """Человекочитаемая подпись группы."""
    key = str(bracket or ALL_BRACKET)
    return BASIC_BRACKET_LABELS.get(key, key)


__all__ = [
    "ALL_BRACKET",
    "BASIC_BRACKETS",
    "BASIC_BRACKET_BY_RANK",
    "BASIC_BRACKET_LABELS",
    "basic_bracket_for_rank",
    "basic_bracket_label",
]
