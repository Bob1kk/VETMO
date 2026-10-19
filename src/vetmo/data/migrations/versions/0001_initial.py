"""Начальная миграция: все таблицы по разделу 7 плана, через create_all.

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.engine import Engine

from vetmo.data.models_orm import Base

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт все таблицы/индексы/ограничения из ORM-метаданных."""
    bind: Engine | None = op.get_bind()
    assert bind is not None
    Base.metadata.create_all(bind)


def downgrade() -> None:
    """Удаляет все таблицы (обратный create_all)."""
    bind2: Engine | None = op.get_bind()
    assert bind2 is not None
    Base.metadata.drop_all(bind2)
