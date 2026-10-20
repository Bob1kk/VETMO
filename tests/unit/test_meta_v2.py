"""R2-тесты meta v2: миграция 0002, тиры, дельты, позиционный фильтр."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.db import create_db, migrate
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import Hero


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    """Временная SQLite, миграции до head (0001 -> 0002)."""
    url = f"sqlite:///{(tmp_path / 'meta_v2.db').as_posix()}"
    engine, sessionmaker = create_db(url)
    migrate(engine, url)
    yield engine, sessionmaker
    engine.dispose()


@pytest.fixture()
def heroes(db_engine: tuple[Engine, sessionmaker[Session]]) -> list[Hero]:
    """Герой 1 = Carry; герой 2 = Support; герой 3 = Mid."""
    _, sessionmaker = db_engine
    repo = HeroRepository(sessionmaker())
    result = [
        Hero(id=1, name="carry-1", localized_name="Carry One",
             primary_attr="agi", attack_type="Melee",
             roles=["Carry", "Escape"], icon_url=None),
        Hero(id=2, name="support-2", localized_name="Support Two",
             primary_attr="int", attack_type="Ranged",
             roles=["Support", "Hard Support"], icon_url=None),
        Hero(id=3, name="mid-3", localized_name="Mid Three",
             primary_attr="int", attack_type="Ranged",
             roles=["Nuker", "Escape"], icon_url=None),
    ]
    for hero in result:
        repo.upsert(hero)
    return result


def _tier_name(tier: int) -> str:
    """Названия тиров 1..8 только для документации в тестах."""
    return [
        "Herald", "Guardian", "Crusader", "Archon",
        "Legend", "Ancient", "Divine", "Immortal",
    ][tier - 1]


def test_migration_0002_schema(db_engine: tuple[Engine, sessionmaker[Session]]) -> None:
    """0002: новые колонки есть, старая unique заменена на (?tатегория tier)+index v2."""
    engine, _ = db_engine
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("meta_snapshots")}
    assert {"ban_rate", "delta_win", "delta_pick", "delta_ban",
            "rank_tier"} <= columns
    uniques = {u["name"] for u in
               inspector.get_unique_constraints("meta_snapshots")}
    assert "uq_meta_patch_hero" not in uniques
    indexes = {
        i["name"]: i["unique"] for i in inspector.get_indexes("meta_snapshots")}
    # SQLite inspector отдаёт 1 в качестве truthy-флага уникального индекса
    assert bool(indexes.get("ix_meta_snapshot_patch_hero_tier"))
    # news_items появилась сразу после миграций
    tables = set(inspector.get_table_names())
    assert "news_items" in tables


def test_migration_0002_from_legacy_with_data(
    tmp_path: Path,
) -> None:
    """0001 -> старая база с данными -> миграция сохраняет их и апгрейдится."""
    import shutil  # noqa: PLC0415

    import alembic.command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    from vetmo.data.db import _migrations_dir  # noqa: PLC0415, SLF001 — путь миграций

    # Клон папки миграций БЕЗ 0002 -> чистая схема 0001 (нужен env.py).
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    engine, _ = create_db(url)
    src_root = Path(_migrations_dir())
    versions = src_root / "versions"
    clone = tmp_path / "migs_0001only"
    (clone / "versions").mkdir(parents=True)
    for root_file in src_root.iterdir():
        if root_file.is_file():
            shutil.copy(root_file, clone / root_file.name)
    for version_file in versions.iterdir():
        if not version_file.is_file() or version_file.name == "0002_meta_v2.py":
            continue
        shutil.copy(version_file, clone / "versions" / version_file.name)
    cfg = Config()
    cfg.set_main_option("script_location", str(clone))
    cfg.set_main_option("sqlalchemy.url", url)
    alembic.command.upgrade(cfg, "0001")

    # Данные в старой схеме (старые колонки, старая unique).
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO patches (id, version) VALUES (1, '7.53')"))
        conn.execute(text(
            "INSERT INTO heroes (name, localized_name, primary_attr, "
            "attack_type, roles, is_validated) VALUES "
            "('h', 'H', 'str', 'Melee', '[]', 1)"))
        conn.execute(text(
            "INSERT INTO meta_snapshots (patch_id, hero_id, win_rate, "
            "pick_rate) VALUES (1, 1, 51.0, 9.0)"))

    migrate(engine, url)  # накатываем 0002

    with engine.begin() as conn:
        data = conn.execute(
            text("SELECT win_rate, pick_rate, ban_rate, rank_tier "
                 "FROM meta_snapshots")).all()
    assert data == [(51.0, 9.0, 0.0, None)]
    engine.dispose()


def test_upsert_tier_rows_and_defaults(
    db_engine: tuple[Engine, sessionmaker[Session]],
    heroes: list[Hero],
) -> None:
    """upsert: tier=None общий тир, 1..8 отдельные строки; ban_rate default."""
    _, sessionmaker = db_engine
    with sessionmaker() as session:
        repo = MetaRepository(session)
        patch = repo.ensure_patch(session, "7.54", None)
        repo.upsert(patch, 1, 51.0, 10.0)  # старый вид вызова (4 аргумента)
        repo.upsert(patch, 1, 49.0, 12.0, rank_tier=3, ban_rate=44.0)
        repo.upsert(patch, 1, 48.0, 14.0, rank_tier=8)
        pub = repo.get_top_meta(limit=100, rank_tier=None)
        tier3 = repo.get_top_meta(limit=100, rank_tier=3)
        tier8 = repo.get_top_meta(limit=100, rank_tier=8)
    assert len(pub) == 1 and pub[0].hero_id == 1
    assert len(tier3) == 1 and tier3[0].win_rate == 49.0
    # Pro-баны не разбиваются по рангам: в tier-строке всегда None даже
    # если старый код записал значение.
    assert tier3[0].ban_rate is None and tier3[0].delta_ban is None
    assert len(tier8) == 1 and tier8[0].win_rate == 48.0
    # 3 строки: None, 3, 8; ban_rate по умолчанию 0
    with sessionmaker() as session:
        repo = MetaRepository(session)
        assert repo.count() == 3
        assert repo.latest_patch_id() == patch
        assert pub[0].ban_rate == 0.0
        assert pub[0].patch_version == "7.54"


def test_delta_calculation_flow(
    db_engine: tuple[Engine, sessionmaker[Session]],
    heroes: list[Hero],
) -> None:
    """Дельты: первый upsert — NULL/0; второй — от прежней строки."""
    _, sessionmaker = db_engine
    with sessionmaker() as session:
        repo = MetaRepository(session)
        patch = repo.ensure_patch(session, "7.54", None)
        repo.upsert(patch, 1, 50.0, 10.0, ban_rate=40.0)
        first = repo.get_top_meta(limit=5)[0]
    assert first.delta_win is None and first.delta_pick is None
    assert first.delta_ban is None
    with sessionmaker() as session:
        repo = MetaRepository(session)
        repo.upsert(patch, 1, 52.0, 11.0, ban_rate=41.5)
        second = repo.get_top_meta(limit=5)[0]
    assert second.win_rate == 52.0
    assert second.delta_win == 2.0
    assert second.delta_pick == 1.0
    assert second.delta_ban == 1.5


def test_position_filter_no_underfill(
    db_engine: tuple[Engine, sessionmaker[Session]],
    heroes: list[Hero],
) -> None:
    """pos-фильтр не теряет строки: SQL LIMIT не применяется до фильтра.

    Регрессия: limit*2 берёт только топ по WR; если там нет героев нужной
    позиции, результат пуст/недобран.
    """
    _, sessionmaker = db_engine
    with sessionmaker() as session:
        repo = HeroRepository(session)
        for hero_id in range(10, 20):
            repo.upsert(Hero(
                id=hero_id, name=f"support-{hero_id}",
                localized_name=f"Support {hero_id}", primary_attr="int",
                attack_type="Ranged", roles=["Hard Support"], icon_url=None))
        for hero_id in range(20, 25):
            repo.upsert(Hero(
                id=hero_id, name=f"carry-{hero_id}",
                localized_name=f"Carry {hero_id}", primary_attr="agi",
                attack_type="Melee", roles=["Carry"], icon_url=None))
    with sessionmaker() as session:
        repo = MetaRepository(session)
        patch = repo.ensure_patch(session, "7.55", None)
        for hero_id in range(10, 20):
            repo.upsert(patch, hero_id, 60.0 - (hero_id - 10) * 0.1, 5.0)
        for hero_id in range(20, 25):
            repo.upsert(patch, hero_id, 49.0 - (hero_id - 20) * 0.1, 5.0)
        rows = repo.get_top_meta(limit=5, position=1)
    assert [row.hero_id for row in rows] == [20, 21, 22, 23, 24]


def test_position_filter(
    db_engine: tuple[Engine, sessionmaker[Session]],
    heroes: list[Hero],
) -> None:
    """position фильтрует по ролям: pos1 -> Carry; pos5 -> Support."""
    _, sessionmaker = db_engine
    with sessionmaker() as session:
        repo = MetaRepository(session)
        patch = repo.ensure_patch(session, "7.54", None)
        repo.upsert(patch, 1, 52.0, 15.0)  # Carry
        repo.upsert(patch, 2, 51.0, 12.0)  # Support
        repo.upsert(patch, 3, 50.0, 20.0)  # Mid
        pos1 = {r.hero_id for r in repo.get_top_meta(limit=10, position=1)}
        pos5 = {r.hero_id for r in repo.get_top_meta(limit=10, position=5)}
        pos2 = {r.hero_id for r in repo.get_top_meta(limit=10, position=2)}
    assert pos1 == {1}
    assert pos5 == {2}
    # pos2: Nuker (поддержив) -> герой 3; Escape (поддержив) -> герой 1
    assert pos2 == {1, 3}
    # positions в MetaRow соответствуют ролям
    with sessionmaker() as session:
        repo = MetaRepository(session)
        rows = {r.hero_id: r for r in repo.get_top_meta(limit=10, rank_tier=None)}
    assert rows[2].positions == [4, 5]
    assert rows[3].positions == [2, 4]
