"""Репозиторий мета-снэпшотов: дедуп по patch+hero. Контракт T-005."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import HeroORM, MetaSnapshotORM, PatchORM
from vetmo.domain.models import Hero


def _to_hero(row: HeroORM) -> Hero:
    """ORM Hero -> доменная модель."""
    return Hero(
        id=row.id, name=row.name, localized_name=row.localized_name,
        primary_attr=row.primary_attr, attack_type=row.attack_type,
        roles=list(row.roles or []), icon_url=row.icon_url,
        is_validated=bool(row.is_validated),
    )


class MetaRepository:
    """Мета по патчу: win_rate, pick_rate; дедуп по (patch_id, hero_id)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def ensure_patch(
        session: Session, version: str,
        release_date: datetime | None, note: str | None = None,
    ) -> int:
        """Получает/создаёт патч, возвращает его id."""
        stmt = sqlite_insert(PatchORM).values(
            version=version, release_date=release_date, note=note,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["version"], set_={"note": stmt.excluded.note})
        session.execute(stmt)
        session.commit()
        row = session.query(PatchORM).filter(PatchORM.version == version).one()
        return row.id

    def upsert(
        self, patch_id: int, hero_id: int,
        win_rate: float, pick_rate: float,
    ) -> None:
        """ON CONFLICT(patch_id, hero_id): значение обновляется."""
        stmt = sqlite_insert(MetaSnapshotORM).values(
            patch_id=patch_id, hero_id=hero_id,
            win_rate=win_rate, pick_rate=pick_rate,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["patch_id", "hero_id"],
            set_={
                "win_rate": stmt.excluded.win_rate,
                "pick_rate": stmt.excluded.pick_rate,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def get_meta(self, hero_id: int) -> tuple[float, float] | None:
        """Последний снэпшот героя: (win_rate, pick_rate) или None."""
        row = (
            self._session.query(MetaSnapshotORM)
            .filter(MetaSnapshotORM.hero_id == hero_id)
            .order_by(MetaSnapshotORM.created_at.desc(), MetaSnapshotORM.id.desc())
            .first()
        )
        return (row.win_rate, row.pick_rate) if row else None

    def get_top_meta(self, limit: int = 10) -> list[tuple[Hero, float, float]]:
        """Топ героев по win_rate: [(Hero, win_rate, pick_rate), ...]."""
        stmt = (
            select(HeroORM, MetaSnapshotORM.win_rate, MetaSnapshotORM.pick_rate)
            .join(MetaSnapshotORM, MetaSnapshotORM.hero_id == HeroORM.id)
            .order_by(MetaSnapshotORM.win_rate.desc())
            .limit(limit)
        )
        rows = self._session.execute(stmt).all()
        return [(_to_hero(r[0]), float(r[1]), float(r[2])) for r in rows]

    def count(self) -> int:
        """Количество снэпшотов."""
        return int(self._session.query(
            func.count(MetaSnapshotORM.id)).scalar() or 0)
