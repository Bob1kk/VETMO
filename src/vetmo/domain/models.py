"""Чистые доменные модели без I/O. Публичный контракт T-006."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Position = int
Team = Literal["radiant", "dire"]

_POSITION_RANGE = range(1, 6)


def validate_position(position: int) -> Position:
    """Проверяет позицию 1..5, возвращает её или ValueError."""
    if position not in _POSITION_RANGE:
        raise ValueError(f"Позиция должна быть 1..5 (invalid position): {position}")
    return position


class Hero(BaseModel):
    """Герой Dota 2 из OpenDota."""

    id: int
    name: str
    localized_name: str
    primary_attr: str
    attack_type: str
    roles: list[str] = Field(default_factory=list)
    icon_url: str | None = None
    is_validated: bool = False


class Pick(BaseModel):
    """Один пик драфта."""

    team: Team
    position: Position
    hero_id: int

    @field_validator("position")
    @classmethod
    def _pos_in_range(cls, v: int) -> int:
        return validate_position(v)


class DraftPick(BaseModel):
    """Пик с номером шага (шаг 0-базированный)."""

    team: Team
    position: Position
    hero_id: int
    step: int

    @field_validator("position")
    @classmethod
    def _pos_in_range(cls, v: int) -> int:
        return validate_position(v)


class DraftSession(BaseModel):
    """Состояние сессии драфта (2-2-1, всего 10 пиков)."""

    id: int | None = None
    current_step: int = 0
    total_picks: int = 10
    picks: list[DraftPick] = Field(default_factory=list)
