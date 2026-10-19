"""Строка мета-топа для UI: герой + win/pick/ban + дельты. Контракт R2 (задача 2)."""

from dataclasses import dataclass, field

from vetmo.domain.models import Hero


@dataclass
class MetaRow:
    """Одна строка мета-топа.

    rank_tier=None соответствует общему паблик-тиру; 1..8 — ранговым.
    delta_* разница относительно предыдущего снэпшота того же ключа
    (None — впервые записано). positions — подходящие позиции 1..5
    по roles героя (POSITION_ROLES).
    """

    hero_id: int
    name: str
    hero: Hero
    win_rate: float
    delta_win: float | None = None
    pick_rate: float = 0.0
    delta_pick: float | None = None
    ban_rate: float = 0.0
    delta_ban: float | None = None
    positions: list[int] = field(default_factory=list)
