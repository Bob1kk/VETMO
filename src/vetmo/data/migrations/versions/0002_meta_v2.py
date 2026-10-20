"""Миграция meta v2: ban_rate/дельты/rank_tier в meta_snapshots + news_items.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Table

from vetmo.data.models_orm import Base, NewsItemORM

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Новые колонки meta_snapshots: {имя: (тип, server_default)}
_NEW_COLUMNS: dict[str, tuple[sa.types.TypeEngine[sa.Any], str | None]] = {
    "ban_rate": (sa.Float(), "0"),
    "delta_win": (sa.Float(), None),
    "delta_pick": (sa.Float(), None),
    "delta_ban": (sa.Float(), None),
    "rank_tier": (sa.Integer(), None),
}


def upgrade() -> None:
    """meta_snapshots: колонки v2 + уникальность (patch, hero, tier); news_items."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("meta_snapshots")}
    with op.batch_alter_table("meta_snapshots") as batch:
        for name, (col_type, server_default) in _NEW_COLUMNS.items():
            if name in columns:
                continue
            if server_default is None:
                batch.add_column(sa.Column(name, col_type, nullable=True))
            else:
                batch.add_column(sa.Column(
                    name, col_type, nullable=False,
                    server_default=sa.text(server_default)))

        # Уникальность v1 (patch_id, hero_id, name=uq_meta_patch_hero) ->
        # v2 — уникальный индекс (patch_id, hero_id, rank_tier).
        existing = {
            u["name"] for u in inspector.get_unique_constraints("meta_snapshots")
        }
        if "uq_meta_patch_hero" in existing:
            batch.drop_constraint("uq_meta_patch_hero", type_="unique")
        indexes = {i["name"] for i in inspector.get_indexes("meta_snapshots")}
        if "ix_meta_snapshot_patch_hero_tier" not in indexes:
            batch.create_index(
                "ix_meta_snapshot_patch_hero_tier",
                ["patch_id", "hero_id", "rank_tier"],
                unique=True,
            )

    # news_items может отсутствовать в БД до R2 (0001 create_all её не знал).
    Base.metadata.create_all(
        bind,
        tables=[cast(Table, NewsItemORM.__table__)],
        checkfirst=True,
    )


def downgrade() -> None:
    """meta_snapshots: обратно к v1 (drop новых колонок и уникальности)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("meta_snapshots")}

    with op.batch_alter_table("meta_snapshots") as batch:
        indexes = {i["name"] for i in inspector.get_indexes("meta_snapshots")}
        if "ix_meta_snapshot_patch_hero_tier" in indexes:
            batch.drop_index("ix_meta_snapshot_patch_hero_tier")
        existing = {
            u["name"] for u in inspector.get_unique_constraints("meta_snapshots")
        }
        if "uq_meta_patch_hero" not in existing and columns:
            batch.create_unique_constraint(
                "uq_meta_patch_hero", ["patch_id", "hero_id"])
        for name in _NEW_COLUMNS:
            if name in columns:
                batch.drop_column(name)

    Base.metadata.drop_all(
        bind,
        tables=[cast(Table, NewsItemORM.__table__)],
        checkfirst=True,
    )
