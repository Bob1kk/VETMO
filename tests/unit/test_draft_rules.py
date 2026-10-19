"""Тесты доменных моделей и правил драфта 2-2-1 (T-006)."""

import pytest
from pydantic import ValidationError

from vetmo.domain.models import DraftPick, DraftSession, Hero, Pick, validate_position
from vetmo.domain.rules import (
    PICK_ORDER,
    TOTAL_PICKS,
    is_valid_step,
    suggest_position,
    team_for_step,
)


def test_pick_order_is_2_2_1_x2() -> None:
    """Последовательность 2 пика -> 2 пика -> 1 пик, цикл x2, по 5 на команду."""
    assert TOTAL_PICKS == 10
    assert PICK_ORDER == (
        "radiant", "radiant", "dire", "dire",
        "radiant", "dire", "dire", "radiant",
        "radiant", "dire",
    )
    assert PICK_ORDER.count("radiant") == 5
    assert PICK_ORDER.count("dire") == 5


def test_team_for_step() -> None:
    """step 0-базированный: шаги 0-1 radiant, 2-3 dire, 4 radiant, ..."""
    expected = ["radiant", "radiant", "dire", "dire", "radiant",
                "dire", "dire", "radiant", "radiant", "dire"]
    assert [team_for_step(s) for s in range(10)] == expected
    with pytest.raises(ValueError, match="invalid step"):
        team_for_step(10)


def test_is_valid_step() -> None:
    """Допустимые шаги 0..9."""
    assert is_valid_step(0) and is_valid_step(9)
    assert not is_valid_step(-1) and not is_valid_step(10)


def test_suggest_position_returns_smallest_free() -> None:
    """suggest_position возвращает наименьшую свободную позицию 1..5."""
    assert suggest_position("radiant", []) == 1
    assert suggest_position("radiant", [1, 2]) == 3
    assert suggest_position("dire", [2, 3, 5]) == 1
    assert suggest_position("radiant", [1, 2, 3]) == 4
    with pytest.raises(ValueError, match="no free positions"):
        suggest_position("radiant", [1, 2, 3, 4, 5])


def test_validate_position() -> None:
    """validate_position принимает 1..5, иначе ValueError."""
    for p in (1, 2, 3, 4, 5):
        assert validate_position(p) == p
    with pytest.raises(ValueError):
        validate_position(0)
    with pytest.raises(ValueError):
        validate_position(6)


def test_pick_model_validates() -> None:
    """Pick валидирует team и position."""
    pick = Pick(team="radiant", position=1, hero_id=1)
    assert pick.position == 1 and pick.team == "radiant"
    with pytest.raises(ValidationError):
        Pick(team="blue", position=1, hero_id=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Pick(team="radiant", position=7, hero_id=1)


def test_hero_model() -> None:
    """Hero: обязательные поля, is_validated по умолчанию False."""
    hero = Hero(
        id=1, name="anti-mage", localized_name="Anti-Mage",
        primary_attr="agi", attack_type="Melee", roles=["Carry", "Escape"],
        icon_url=None,
    )
    assert hero.is_validated is False
    assert hero.roles == ["Carry", "Escape"]


def test_draft_session_defaults_and_draft_pick() -> None:
    """DraftSession: id=None, current_step=0, total_picks=10, пустые пики."""
    hero = Hero(id=1, name="x", localized_name="X", primary_attr="str",
                attack_type="Melee", roles=[], icon_url=None)
    dp = DraftPick(team="radiant", position=1, hero_id=hero.id, step=0)
    session = DraftSession()
    assert session.id is None
    assert session.current_step == 0
    assert session.total_picks == 10
    assert session.picks == []
    session.picks = [dp]
    session.current_step = 1
    assert session.picks[0].team == "radiant"
