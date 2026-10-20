"""Контракт строки мета-отчёта для UI: герой + win/pick/ban + позиции."""

from dataclasses import dataclass, field

from vetmo.domain.models import Hero


@dataclass(frozen=True)
class PatchInfo:
    """Патч для поиска/выбора в UI."""

    id: int
    version: str
    release_date: str | None = None
    is_current: bool = False


@dataclass(frozen=True)
class PositionStat:
    """Популярность и винрейт героя на конкретной позиции."""

    position: int
    pick_share: float | None = None
    win_rate: float | None = None
    match_count: int = 0


@dataclass
class MetaRow:
    """Нормализованная строка мета-отчёта.

    positions — только реальные популярные позиции из STRATZ, а не роли героя.
    delta_* — изменение за 7 дней; None, если истории ещё нет.
    ban_scope — группа рангов для ladder-банов (STRATZ отдаёт баны группами).
    """

    hero_id: int
    name: str
    hero: Hero
    win_rate: float
    delta_win: float | None = None
    pick_rate: float = 0.0
    delta_pick: float | None = None
    ban_rate: float | None = None
    delta_ban: float | None = None
    positions: list[int] = field(default_factory=list)
    position_stats: dict[int, PositionStat] = field(default_factory=dict)
    patch_version: str | None = None
    patch_id: int | None = None
    match_count: int = 0
    ban_scope: str | None = None
    sample_reliable: bool = False
