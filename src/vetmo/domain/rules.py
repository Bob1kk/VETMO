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


# ---------------------------------------------------------------------------
# Роли героев по позициям 1-5 (game-agent, интеграция со скорингом).

# Почему так: у каждой позиции есть ровно ОДНА первичная роль — она задаёт
# "профиль" позиции и должна доминировать в скоринге. Если бы все роли
# считались равнозначными, позиции размывались бы (герой "support+nuker"
# поднимался бы и на pos 1, и на pos 5), и рекомендации переставали бы
# различать carry-пик от саппорта. Поэтому position_fit даёт 1.0 только за
# совпадение с первичной ролью позиции, а поддерживающие роли дают пониженный
# бонус 0.6 — они учитываются, но не могут переманить героя на чужую позицию.
#
# Формат первого элемента кортежа = первичная роль позиции, остальные —
# поддерживающие. У OpenDota роли приходят ("Carry", "Escape", "Nuker",
# "Initiator", "Disabler", "Jungler", "Durable", "Support", "Hard Support",
# "Pusher"); нормализуем к snake_case при сравнении. Роль "mid" в данных
# OpenDota отсутствует, поэтому для pos 2 первичной оставлен "mid" (контракт
# роли, фактически не совпадёт), а "nuker"/"escape"/"initiator" работают как
# поддерживающие.
POSITION_ROLES: dict[int, tuple[str, ...]] = {
    1: ("carry",),
    2: ("mid", "nuker", "initiator", "escape"),
    3: ("initiator", "durable", "disabler"),
    4: ("support", "disabler", "escape", "jungler"),
    5: ("hard_support", "support", "disabler"),
}

_FIT_PRIMARY = 1.0
_FIT_SUPPORTING = 0.6
_FIT_NONE = 0.0


def _normalize_role(role: str) -> str:
    """'Hard Support' -> 'hard_support' (сравнение независимо от формата API)."""
    return role.strip().lower().replace(" ", "_").replace("-", "_")


def position_fit(hero_roles: tuple[str, ...], position: int) -> float:
    """Соответствие ролей героя позиции 1..5 для скоринга рекомендаций.

    1.0  — точное совпадение первичной (первой) роли позиции;
    0.6  — совпадает хотя бы одна поддерживающая роль;
    0.0  — совпадений нет (или позиции вне 1..5 / ролей нет).
    """
    mapping = POSITION_ROLES.get(position)
    if not mapping:
        return _FIT_NONE
    if not hero_roles:
        return _FIT_NONE
    roles = {_normalize_role(r) for r in hero_roles}
    if _normalize_role(mapping[0]) in roles:
        return _FIT_PRIMARY
    if any(_normalize_role(r) in roles for r in mapping[1:]):
        return _FIT_SUPPORTING
    return _FIT_NONE
