"""Репозиторий контрпиков: дедуп по паре (hero_id, counter_hero_id). T-005."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import HeroCounterORM, HeroORM
from vetmo.domain.models import Hero

_MIN_SAMPLE = 100  # порог достоверной выборки (R2: все пары, games >= 100)


def _to_hero(row: HeroORM) -> Hero:
    """ORM Hero -> доменная модель."""
    return Hero(
        id=row.id, name=row.name, localized_name=row.localized_name,
        primary_attr=row.primary_attr, attack_type=row.attack_type,
        roles=list(row.roles or []), icon_url=row.icon_url,
        is_validated=bool(row.is_validated),
    )


class CounterRepository:
    """Контрпики: 'faces' — кто контрит героя; 'counters' — кого герой контрит."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self, hero_id: int, counter_hero_id: int,
        win_rate_against: float, sample_size: int,
    ) -> None:
        """ON CONFLICT(hero_id, counter_hero_id): значения обновляются."""
        stmt = sqlite_insert(HeroCounterORM).values(
            hero_id=hero_id, counter_hero_id=counter_hero_id,
            win_rate_against=win_rate_against, sample_size=sample_size,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["hero_id", "counter_hero_id"],
            set_={
                "win_rate_against": stmt.excluded.win_rate_against,
                "sample_size": stmt.excluded.sample_size,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def get_counters_hero_faces(self, hero_id: int) -> list[tuple[Hero, float, int]]:
        """Кто контрит героя hero_id: [(Hero, win_rate_against, sample), ...].

        Строка (hero_id=A, counter_hero_id=B, win) означает: герой A
        контрит героя B, win — процент побед A против B.
        """
        stmt = (
            select(HeroORM, HeroCounterORM.win_rate_against,
                   HeroCounterORM.sample_size)
            .join(HeroCounterORM, HeroCounterORM.hero_id == HeroORM.id)
            .where(HeroCounterORM.counter_hero_id == hero_id)
            .order_by(HeroCounterORM.win_rate_against.desc())
        )
        rows = self._session.execute(stmt).all()
        return [(_to_hero(r[0]), float(r[1]), int(r[2])) for r in rows]

    def get_hero_counters(self, hero_id: int) -> list[tuple[Hero, float, int]]:
        """Кого герой hero_id контрит: [(Hero, win_rate_against, sample), ...]."""
        stmt = (
            select(HeroORM, HeroCounterORM.win_rate_against,
                   HeroCounterORM.sample_size)
            .join(HeroCounterORM, HeroCounterORM.counter_hero_id == HeroORM.id)
            .where(HeroCounterORM.hero_id == hero_id)
            .order_by(HeroCounterORM.win_rate_against.desc())
        )
        rows = self._session.execute(stmt).all()
        return [(_to_hero(r[0]), float(r[1]), int(r[2])) for r in rows]

    def _top_pairs(
        self, hero_id: int, by_hero: bool, limit: int,
    ) -> list[tuple[Hero, float, int]]:
        """Топ пар по win_rate (выборка >= _MIN_SAMPLE).

        by_hero=True  — кого контрит hero_id (join по counter_hero_id);
        by_hero=False — кто контрит hero_id (join по hero_id строки).
        """
        stmt = select(HeroORM, HeroCounterORM.win_rate_against,
                      HeroCounterORM.sample_size)
        join_col = (
            HeroCounterORM.counter_hero_id if by_hero else HeroCounterORM.hero_id)
        stmt = stmt.join(
            HeroCounterORM, join_col == HeroORM.id)
        where_col = (
            HeroCounterORM.hero_id if by_hero else HeroCounterORM.counter_hero_id)
        stmt = (
            stmt.where(where_col == hero_id)
            .where(HeroCounterORM.sample_size >= _MIN_SAMPLE)
            .order_by(HeroCounterORM.win_rate_against.desc())
            .limit(max(0, limit))
        )
        rows = self._session.execute(stmt).all()
        return [(_to_hero(r[0]), float(r[1]), int(r[2])) for r in rows]

    def top_advantages(self, hero_id: int, limit: int = 5) -> list[tuple[Hero, float]]:
        """Герои, которых hero_id контрит: [(Hero, win против них), ...] top-N."""
        return [(hero, win) for hero, win, _sample in (
            self._top_pairs(hero_id, True, limit))]

    def top_disadvantages(self, hero_id: int, limit: int = 5) -> list[tuple[Hero, float]]:
        """Герои, которые контрят hero_id: [(Hero, win против hero), ...] top-N."""
        return [(hero, win) for hero, win, _sample in (
            self._top_pairs(hero_id, False, limit))]
