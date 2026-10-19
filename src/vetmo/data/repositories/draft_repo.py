"""Репозиторий драфта: сессии и пики. Контракт T-005."""

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from vetmo.data.models_orm import DraftPickORM, DraftSessionORM
from vetmo.domain.models import DraftPick, DraftSession, Pick, Team


def _to_domain_session(
    row: DraftSessionORM, picks: list[DraftPick],
) -> DraftSession:
    """ORM сессия -> доменная модель (DraftSession.picks состоит из DraftPick)."""
    return DraftSession(
        id=row.id, current_step=row.current_step,
        total_picks=row.total_picks, picks=picks,
    )


def _load_draft_picks(session: Session, session_id: int) -> list[DraftPick]:
    """Пик-лист сессии как DraftPick (с шагом), упорядочен по step."""
    rows = (
        session.query(DraftPickORM)
        .filter(DraftPickORM.session_id == session_id)
        .order_by(DraftPickORM.step)
        .all()
    )
    return [
        DraftPick(team=cast(Team, r.team), position=r.position, hero_id=r.hero_id, step=r.step)
        for r in rows
    ]


class DraftRepository:
    """Сессии драфта (2-2-1) и их пики."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_session(self) -> DraftSession:
        """Создаёт новую сессию с total_picks=10."""
        row = DraftSessionORM(current_step=0, total_picks=10)
        self._session.add(row)
        self._session.commit()
        return _to_domain_session(row, [])

    def add_pick(self, session_id: int, pick: Pick, step: int) -> None:
        """Добавляет пик и увеличивает current_step до step + 1."""
        row = DraftPickORM(
            session_id=session_id, team=pick.team, position=pick.position,
            hero_id=pick.hero_id, picked_at=datetime.now(), step=step,
        )
        self._session.add(row)
        self._session.query(DraftSessionORM).filter(
            DraftSessionORM.id == session_id
        ).update({"current_step": step + 1})
        self._session.commit()

    def get_session(self, session_id: int) -> DraftSession | None:
        """Сессия с пик-листом или None."""
        row = self._session.get(DraftSessionORM, session_id)
        if row is None:
            return None
        return _to_domain_session(row, _load_draft_picks(self._session, session_id))

    def get_picks(self, session_id: int) -> list[Pick]:
        """Пик-лист сессии в порядке шагов (без step)."""
        return [
            Pick(team=p.team, position=p.position, hero_id=p.hero_id)
            for p in _load_draft_picks(self._session, session_id)
        ]

    def finish_session(self, session_id: int) -> None:
        """Помечает сессию завершённой (finished_at=now)."""
        self._session.query(DraftSessionORM).filter(
            DraftSessionORM.id == session_id
        ).update({"finished_at": datetime.now()})
        self._session.commit()

    def list_sessions(self) -> list[DraftSession]:
        """Все сессии (для истории)."""
        rows = self._session.scalars(select(DraftSessionORM)).all()
        return [
            _to_domain_session(r, _load_draft_picks(self._session, r.id))
            for r in rows
        ]
