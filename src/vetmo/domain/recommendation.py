"""Рекомендация героя с разложением счёта.

``counter`` — средний винрейт героя против врагов минус 50 (п.п.),
``synergy`` — то же для связок с союзниками. UI выбирает причину карточки
по этим компонентам, а не по суммарному счёту.
"""

from dataclasses import dataclass

from vetmo.domain.models import Hero


@dataclass(frozen=True)
class Recommendation:
    """Кандидат на пик с компонентами скоринга."""

    hero: Hero
    score: float
    counter: float = 0.0
    synergy: float = 0.0
    meta_win_rate: float | None = None


__all__ = ["Recommendation"]
