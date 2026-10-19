"""Правила драфта All Pick: порядок пиков 2-2-1, два полных цикла. Контракт T-006."""

from vetmo.domain.models import Team

TOTAL_PICKS = 10

# Цикл "2 пика -> 2 пика -> 1 пик", цикл x2. Всего по 5 пиков на команду.
PICK_ORDER: tuple[Team, ...] = (
    "radiant", "radiant", "dire", "dire",
    "radiant",
    "dire", "dire", "radiant",
    "radiant", "dire",
)
assert len(PICK_ORDER) == TOTAL_PICKS  # noqa: S101 — защита контракта на импорте


def is_valid_step(step: int) -> bool:
    """Шаг валиден, если 0 <= step < TOTAL_PICKS (0-базированный)."""
    return 0 <= step < TOTAL_PICKS


def team_for_step(step: int) -> Team:
    """Возвращает команду, которая пикает на шаге step (0-базированный)."""
    if not is_valid_step(step):
        raise ValueError(f"Некорректный шаг драфта (invalid step): {step}")
    return PICK_ORDER[step]


def suggest_position(team: Team, taken_positions: list[int]) -> int:
    """Наименьшая свободная позиция 1..5 для данной команды."""
    taken = set(taken_positions)
    for pos in range(1, 6):
        if pos not in taken:
            return pos
    raise ValueError(f"Нет свободных позиций для команды {team} (no free positions)")
