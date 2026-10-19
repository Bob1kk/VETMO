"""Репозиторий синергий: дедуп по паре (hero_id, synergy_hero_id). T-005."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import HeroORM, HeroSynergyORM
from vetmo.domain.models import Hero


def _to_hero(row: HeroORM) -> Hero:
    """ORM Hero -> доменная модель."""
    return Hero(
        id=row.id, name=row.name, localized_name=row.localized_name,
        primary_attr=row.primary_attr, attack_type=row.attack_type,
        roles=list(row.roles or []), icon_url=row.icon_url,
        is_validated=bool(row.is_validated),
    )


class SynergyRepository:
    """Синергии: с кем герой работает лучше всего."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self, hero_id: int, synergy_hero_id: int,
        win_rate_with: float, sample_size: int,
    ) -> None:
        """ON CONFLICT(hero_id, synergy_hero_id): значения обновляются."""
        stmt = sqlite_insert(HeroSynergyORM).values(
            hero_id=hero_id, synergy_hero_id=synergy_hero_id,
            win_rate_with=win_rate_with, sample_size=sample_size,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["hero_id", "synergy_hero_id"],
            set_={
                "win_rate_with": stmt.excluded.win_rate_with,
                "sample_size": stmt.excluded.sample_size,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def get_synergies(self, hero_id: int) -> list[tuple[Hero, float, int]]:
        """Синергии героя: [(Hero, win_rate_with, sample), ...] по win_rate desc."""
        stmt = (
            select(HeroORM, HeroSynergyORM.win_rate_with,
                   HeroSynergyORM.sample_size)
            .join(HeroSynergyORM, HeroSynergyORM.synergy_hero_id == HeroORM.id)
            .where(HeroSynergyORM.hero_id == hero_id)
            .order_by(HeroSynergyORM.win_rate_with.desc())
        )
        rows = self._session.execute(stmt).all()
        return [(_to_hero(r[0]), float(r[1]), int(r[2])) for r in rows]
