"""SQLAlchemy 2.x ORM-таблицы точно по разделу 7 плана. Контракт T-004."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """База ORM-моделей."""


class HeroORM(Base):
    """Таблица heroes: уникальный name — ключ upsert."""

    __tablename__ = "heroes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    localized_name: Mapped[str] = mapped_column(String, nullable=False)
    primary_attr: Mapped[str] = mapped_column(String, nullable=False)
    attack_type: Mapped[str] = mapped_column(String, nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    icon_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_heroes_name", "name"),
        Index("ix_heroes_is_validated", "is_validated"),
    )


class PatchORM(Base):
    """Таблица patches."""

    __tablename__ = "patches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    release_date: Mapped[object] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_patches_version", "version"),)


class MetaSnapshotORM(Base):
    """Мета-снэпшот по патчу и герою; дедуп прикладывается в репозитории."""

    __tablename__ = "meta_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patch_id: Mapped[int] = mapped_column(
        ForeignKey("patches.id"), nullable=True)
    hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    pick_rate: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_meta_snapshot_patch_hero", "patch_id", "hero_id"),
        UniqueConstraint("patch_id", "hero_id", name="uq_meta_patch_hero"),
        CheckConstraint("win_rate BETWEEN 0 AND 100", name="ck_meta_win_rate"),
        CheckConstraint("pick_rate BETWEEN 0 AND 100", name="ck_meta_pick_rate"),
    )


class HeroCounterORM(Base):
    """Контрпики: кто контрит героя и какого героя контрит кто."""

    __tablename__ = "hero_counters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    counter_hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    win_rate_against: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_counters_hero_pair", "hero_id", "counter_hero_id"),
        UniqueConstraint("hero_id", "counter_hero_id", name="uq_counter_pair"),
        CheckConstraint(
            "win_rate_against BETWEEN 0 AND 100", name="ck_counter_win_rate"),
    )


class HeroSynergyORM(Base):
    """Синергии: герой в паре с другим героем."""

    __tablename__ = "hero_synergies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    synergy_hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    win_rate_with: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_synergies_hero_pair", "hero_id", "synergy_hero_id"),
        UniqueConstraint("hero_id", "synergy_hero_id", name="uq_synergy_pair"),
        CheckConstraint(
            "win_rate_with BETWEEN 0 AND 100", name="ck_synergy_win_rate"),
    )


class UserSettingORM(Base):
    """Простое KV-хранилище настроек."""

    __tablename__ = "user_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("ix_settings_key", "key"),)


class DraftSessionORM(Base):
    """Сессия драфта (2-2-1)."""

    __tablename__ = "draft_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_picks: Mapped[int] = mapped_column(Integer, default=10)


class DraftPickORM(Base):
    """Пик в сессии драфта."""

    __tablename__ = "draft_picks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("draft_sessions.id"), nullable=False)
    team: Mapped[str] = mapped_column(String(10), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    hero_id: Mapped[int] = mapped_column(
        ForeignKey("heroes.id"), nullable=False)
    picked_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_picks_session_team", "session_id", "team"),
        CheckConstraint("position BETWEEN 1 AND 5", name="ck_pick_position"),
    )
