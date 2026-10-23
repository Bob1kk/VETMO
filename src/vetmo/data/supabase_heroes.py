"""Каталог героев из Supabase с локальным seed-фолбэком.

Supabase — источник истины. JSON-файл нужен только для двух случаев:
1) миграция ещё не применена / сеть недоступна — UI не остаётся пустым;
2) exe запущен до первого sync.

Каталог кэшируется в памяти: 127 героев меняются только с патчем.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from vetmo.domain.models import Hero
from vetmo.infra.supabase_gateway import SupabaseGateway

logger = logging.getLogger("vetmo.heroes")

_HERO_COLUMNS = (
    "id,name,localized_name,primary_attr,attack_type,roles,icon_url,is_validated"
)


def _seed_path() -> Path:
    return Path(__file__).resolve().parent / "heroes_seed.json"


def load_seed_heroes() -> list[Hero]:
    """Герои из упакованного JSON (127 записей)."""
    try:
        raw = json.loads(_seed_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Не удалось прочитать heroes_seed.json")
        return []
    heroes: list[Hero] = []
    for row in raw:
        try:
            heroes.append(Hero.model_validate(row))
        except Exception:  # noqa: BLE001 - один битый ряд не должен ронять каталог
            continue
    return heroes


class SupabaseHeroRepository:
    """Read-only каталог героев: Supabase -> seed JSON."""

    def __init__(self, gateway: SupabaseGateway) -> None:
        self._gateway = gateway
        self._cache: list[Hero] | None = None

    def get_all(self) -> list[Hero]:
        """Все герои по возрастанию id."""
        if self._cache is not None:
            return list(self._cache)
        rows: list[dict] = []
        if self._gateway.is_configured:
            try:
                rows = self._gateway.select(
                    "vetmo_heroes",
                    columns=_HERO_COLUMNS,
                    order=("id", False),
                )
            except Exception as exc:  # noqa: BLE001 - фолбэк на seed
                logger.warning("Каталог из Supabase недоступен: %s", type(exc).__name__)
        if rows:
            heroes = []
            for row in rows:
                try:
                    heroes.append(Hero.model_validate(row))
                except Exception:  # noqa: BLE001
                    continue
            self._cache = heroes
        else:
            self._cache = load_seed_heroes()
        return list(self._cache)

    def get_by_id(self, hero_id: int) -> Hero | None:
        """Герой по id или None."""
        return next((h for h in self.get_all() if h.id == int(hero_id)), None)

    def count(self) -> int:
        """Количество героев в каталоге."""
        return len(self.get_all())

    def first_hero_ids(self, limit: int = 10) -> list[int]:
        """Первые limit id (для совместимости со старым API)."""
        return [h.id for h in self.get_all()[: max(0, limit)]]

    def invalidate(self) -> None:
        """Сбрасывает кэш после sync/ручного обновления."""
        self._cache = None


__all__ = ["SupabaseHeroRepository", "load_seed_heroes"]
