"""Репозиторий героев: upsert ON CONFLICT(name) — идемпотентно. Контракт T-004."""

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import HeroORM
from vetmo.domain.models import Hero


def _to_domain(row: HeroORM) -> Hero:
    """ORM -> доменная модель."""
    return Hero(
        id=row.id,
        name=row.name,
        localized_name=row.localized_name,
        primary_attr=row.primary_attr,
        attack_type=row.attack_type,
        roles=list(row.roles or []),
        icon_url=row.icon_url,
        is_validated=bool(row.is_validated),
    )


class HeroRepository:
    """CRUD по таблице heroes. Конструируется от открытой Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_all(self) -> list[Hero]:
        """Все герои как доменные модели."""
        rows = self._session.query(HeroORM).order_by(HeroORM.id).all()
        return [_to_domain(r) for r in rows]

    def get_by_id(self, hero_id: int) -> Hero | None:
        """Герой по PK или None."""
        row = self._session.get(HeroORM, hero_id)
        return _to_domain(row) if row else None

    def get_by_name(self, name: str) -> Hero | None:
        """Герой по уникальному имени или None."""
        row = (
            self._session.query(HeroORM)
            .filter(HeroORM.name == name)
            .first()
        )
        return _to_domain(row) if row else None

    def count(self) -> int:
        """Количество героев в таблице."""
        return int(self._session.query(func.count(HeroORM.id)).scalar() or 0)

    def upsert(self, hero: Hero) -> None:
        """ON CONFLICT(name) DO UPDATE: без дублей, поля обновляются."""
        stmt = sqlite_insert(HeroORM).values(
            id=hero.id if hero.id is not None else None,
            name=hero.name,
            localized_name=hero.localized_name,
            primary_attr=hero.primary_attr,
            attack_type=hero.attack_type,
            roles=hero.roles,
            icon_url=hero.icon_url,
            is_validated=hero.is_validated,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={
                "localized_name": stmt.excluded.localized_name,
                "primary_attr": stmt.excluded.primary_attr,
                "attack_type": stmt.excluded.attack_type,
                "roles": stmt.excluded.roles,
                "icon_url": stmt.excluded.icon_url,
                "is_validated": stmt.excluded.is_validated,
            },
        )
        self._session.execute(stmt)
        self._session.commit()
