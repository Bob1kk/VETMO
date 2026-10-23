"""Тесты сборки блока подсказок оверлея (dedupe + сортировка по score)."""

from __future__ import annotations

from vetmo.domain.models import Hero
from vetmo.ui.viewmodels.overlay_vm import OverlayEntry, _flatten_suggestions


def _hero(hero_id: int, name: str) -> Hero:
    return Hero(
        id=hero_id, name=f"npc_dota_hero_{hero_id}", localized_name=name,
        primary_attr="str", attack_type="Melee", roles=["Carry"],
        icon_url=None, is_validated=True,
    )


def _entry(hero_id: int, score: float, position: int) -> OverlayEntry:
    return OverlayEntry(
        hero=_hero(hero_id, f"Hero {hero_id}"), score=score,
        reason="Мета", position=position,
    )


def test_flatten_suggestions_dedupes_and_sorts() -> None:
    """Один герой не повторяется; порядок — по убыванию score."""
    columns = {
        1: [_entry(10, 5.0, 1), _entry(11, 3.0, 1)],
        2: [_entry(10, 5.0, 2), _entry(12, 9.0, 2)],
    }
    result = _flatten_suggestions(columns, limit=4)

    assert [entry.hero.id for entry in result] == [12, 10, 11]
    assert result[0].position == 2


def test_flatten_suggestions_respects_limit() -> None:
    """Лимит обрезает список подсказок."""
    columns = {1: [_entry(hero_id, float(hero_id), 1) for hero_id in (10, 11, 12)]}
    result = _flatten_suggestions(columns, limit=2)
    assert [entry.hero.id for entry in result] == [12, 11]


def test_flatten_suggestions_handles_empty_columns() -> None:
    """Пустые колонки и нулевой лимит дают пустой список."""
    assert _flatten_suggestions({}, limit=4) == []
    assert _flatten_suggestions({1: [_entry(10, 1.0, 1)]}, limit=0) == []
