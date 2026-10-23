"""Причины карточек оверлея по компонентам скоринга.

Порядок важен: контр-пик -> связка -> мета -> подбор по позициям.
Так подсказка объясняет, почему герой в списке.
"""

from __future__ import annotations

from vetmo.domain.models import Hero
from vetmo.domain.recommendation import Recommendation
from vetmo.ui.viewmodels.overlay_vm import _reason_from_detail

_HERO = Hero(
    id=1, name="test", localized_name="Test",
    primary_attr="str", attack_type="Melee", roles=["Carry"],
    icon_url=None, is_validated=True,
)


def _rec(**kwargs) -> Recommendation:
    return Recommendation(hero=_HERO, score=10.0, **kwargs)


def test_strong_counter_is_labeled_counter() -> None:
    assert _reason_from_detail(_rec(counter=2.5), 1) == "Контр-пик"


def test_weak_counter_falls_through_to_synergy() -> None:
    rec = _rec(counter=1.0, synergy=2.0)
    assert _reason_from_detail(rec, 1) == "Связка"


def test_meta_reason_needs_positive_win_rate() -> None:
    assert _reason_from_detail(_rec(meta_win_rate=51.5), 1) == "Мета"
    assert (
        _reason_from_detail(_rec(meta_win_rate=50.9), 1)
        == "Подбор по позициям"
    )
