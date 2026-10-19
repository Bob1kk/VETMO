"""Репозиторий мета-снэпшотов v2: дедуп (patch, hero, rank_tier) + дельты. R2."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import HeroORM, MetaSnapshotORM, PatchORM
from vetmo.domain.meta_row import MetaRow
from vetmo.domain.models import Hero
from vetmo.domain.rules import position_fit


def _to_hero(row: HeroORM) -> Hero:
    """ORM Hero -> доменная модель."""
    return Hero(
        id=row.id, name=row.name, localized_name=row.localized_name,
        primary_attr=row.primary_attr, attack_type=row.attack_type,
        roles=list(row.roles or []), icon_url=row.icon_url,
        is_validated=bool(row.is_validated),
    )


def _positions(roles: list[str]) -> list[int]:
    """Позиции 1..5 героя по его ролям (POSITION_ROLES через position_fit)."""
    return [p for p in range(1, 6) if position_fit(tuple(roles), p) > 0.0]


class MetaRepository:
    """Мета по патчу: win/pick/ban per (patch_id, hero_id, rank_tier) + дельты."""

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

    def _get_snapshot(
        self, patch_id: int, hero_id: int, rank_tier: int | None,
    ) -> MetaSnapshotORM | None:
        """Текущий снэпшот для ключа (patch, hero, tier); tier IS NULL-aware."""
        query = self._session.query(MetaSnapshotORM).filter(
            MetaSnapshotORM.patch_id == patch_id,
            MetaSnapshotORM.hero_id == hero_id,
        )
        query = (
            query.filter(MetaSnapshotORM.rank_tier.is_(None))
            if rank_tier is None
            else query.filter(MetaSnapshotORM.rank_tier == rank_tier)
        )
        return query.first()

    def upsert(
        self, patch_id: int, hero_id: int,
        win_rate: float, pick_rate: float, rank_tier: int | None = None,
        ban_rate: float = 0.0,
    ) -> None:
        """Дедуп по (patch, hero, rank_tier); дельты считаются ДО перезаписи.

        delta_* = новое значение - текущее той же строки; None, если это
        первая запись для ключа. Полностью обратно совместимо: вызовы вида
        upsert(patch, hero, win, pick) работают (rank_tier=None, ban 0).
        """
        existing = self._get_snapshot(patch_id, hero_id, rank_tier)
        if existing is None:
            self._session.add(MetaSnapshotORM(
                patch_id=patch_id, hero_id=hero_id,
                win_rate=win_rate, pick_rate=pick_rate, ban_rate=ban_rate,
                delta_win=None, delta_pick=None, delta_ban=None,
                rank_tier=rank_tier,
            ))
            self._session.commit()
            return
        delta_win = round(win_rate - existing.win_rate, 2)
        delta_pick = round(pick_rate - existing.pick_rate, 2)
        delta_ban = round(ban_rate - (existing.ban_rate or 0.0), 2)
        existing.win_rate = win_rate
        existing.pick_rate = pick_rate
        existing.ban_rate = ban_rate
        existing.delta_win = delta_win
        existing.delta_pick = delta_pick
        existing.delta_ban = delta_ban
        self._session.commit()

    def get_meta(self, hero_id: int) -> tuple[float, float] | None:
        """Снэпшот героя (предпочтительно общий тир): (win_rate, pick_rate)."""
        base = (
            self._session.query(MetaSnapshotORM)
            .filter(MetaSnapshotORM.hero_id == hero_id)
        )
        row = base.filter(MetaSnapshotORM.rank_tier.is_(None)).first()
        if row is None:
            row = base.order_by(MetaSnapshotORM.rank_tier.desc()).first()
        return (row.win_rate, row.pick_rate) if row else None

    def _to_meta_row(self, hero_orm: HeroORM, snapshot: MetaSnapshotORM) -> MetaRow:
        """(HeroORM, MetaSnapshotORM) -> MetaRow для UI."""
        return MetaRow(
            hero_id=snapshot.hero_id,
            name=hero_orm.name,
            hero=_to_hero(hero_orm),
            win_rate=float(snapshot.win_rate),
            delta_win=(
                float(snapshot.delta_win)
                if snapshot.delta_win is not None else None),
            pick_rate=float(snapshot.pick_rate),
            delta_pick=(
                float(snapshot.delta_pick)
                if snapshot.delta_pick is not None else None),
            ban_rate=float(snapshot.ban_rate or 0.0),
            delta_ban=(
                float(snapshot.delta_ban)
                if snapshot.delta_ban is not None else None),
            positions=_positions(list(hero_orm.roles or [])),
        )

    def get_top_meta(
        self, limit: int = 10,
        rank_tier: int | None = None, position: int | None = None,
    ) -> list[MetaRow]:
        """Топ героев по win_rate как MetaRow (контракт R2, см. domain/meta_row.py).

        rank_tier: None — общий тир (rank_tier IS NULL), 1..8 — ранговый тир.
        position: 1..5 — фильтр по ролям героя (POSITION_ROLES); None — без фильтра.
        """
        tier_expr = MetaSnapshotORM.rank_tier.is_(None) if rank_tier is None else (
            MetaSnapshotORM.rank_tier == rank_tier
        )
        stmt = (
            select(HeroORM, MetaSnapshotORM)
            .join(
                MetaSnapshotORM, MetaSnapshotORM.hero_id == HeroORM.id)
            .where(tier_expr)
            .order_by(
                MetaSnapshotORM.win_rate.desc(), MetaSnapshotORM.pick_rate.desc(),
                HeroORM.localized_name.asc())
            .limit(max(0, limit) * 2 if position else limit)
        )
        rows = self._session.execute(stmt).all()
        result: list[MetaRow] = []
        for hero_orm, snapshot in rows:
            if position is not None and position not in _positions(
                    list(hero_orm.roles or [])):
                continue
            result.append(self._to_meta_row(hero_orm, snapshot))
            if len(result) >= max(0, limit):
                break
        return result

    def latest_patch_id(self) -> int | None:
        """id последнего созданного патча (max id) или None, если пусто."""
        row = self._session.query(func.max(PatchORM.id)).scalar()
        return int(row) if row is not None else None

    def count(self) -> int:
        """Количество снэпшотов."""
        return int(self._session.query(
            func.count(MetaSnapshotORM.id)).scalar() or 0)
