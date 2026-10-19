"""R2-тесты sync_matchups_all: все пары, min_games, resume по ключу settings."""

import json

import httpx

from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.services.opendota_client import OpenDotaClient
from vetmo.services.validator_service import ValidatorService

# Матчапы: {hero_id: [(against, games, wins героя против against), ...]}
MATCHUPS: dict[int, list[tuple[int, int, int]]] = {
    1: [(2, 5000, 2600), (3, 300, 140), (4, 80, 40)],   # 4/80 < min_games
    2: [(1, 5000, 2400), (3, 200, 110), (4, 250, 130)],
    3: [(1, 300, 160), (2, 200, 90), (4, 150, 70)],
    4: [(1, 250, 130), (2, 250, 120), (3, 150, 80)],
}


def _fast_settings() -> Settings:
    """Без .env; интервал лимита быстрый для тестов."""
    return Settings(_env_file=None, rate_limit_per_min=1200)


def _hero(hero_id: int) -> Hero:
    """Заглушка героя для seeding."""
    return Hero(
        id=hero_id, name=f"npc_{hero_id}", localized_name=f"Hero {hero_id}",
        primary_attr="str", attack_type="Melee", roles=[], icon_url=None)


def _seed_heroes(db) -> None:
    _, sessionmaker = db
    with sessionmaker() as session:
        repo = HeroRepository(session)
        for hero_id in MATCHUPS:
            repo.upsert(_hero(hero_id))


def _mk_client(db, call_fail_hero: int | None = None) -> OpenDotaClient:
    """Клиент над временной БД с mock-транспортом и без задержек."""
    engine, sessionmaker = db
    client = OpenDotaClient(
        settings=_fast_settings(), validator=ValidatorService(),
        engine=engine, sessionmaker=sessionmaker,
        http_client=httpx.Client(transport=httpx.MockTransport(
            _handler(call_fail_hero))),
    )
    client.retry_delays = (0.0, 0.0, 0.0)
    return client


def _handler(call_fail_hero: int | None = None):
    """Mock-хендлер matchup-эндпоинта; опционально герой с сетевым сбоем."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if "/matchups" in path:
            hero_id = int(path.split("/")[-2])
            if hero_id == call_fail_hero:
                raise httpx.ConnectError("boom")
            rows = [
                {"hero_id": hero_id, "against_hero_id": against,
                 "games_played": games, "wins": wins}
                for against, games, wins in MATCHUPS.get(hero_id, [])
            ]
            return httpx.Response(200, json=rows)
        return httpx.Response(404, json={})

    return handler


def test_sync_matchups_all_all_pairs(db) -> None:
    """Все пары с games >= 100 сохраняются; результат по контракту."""
    _seed_heroes(db)
    client = _mk_client(db)
    result = client.sync_matchups_all()
    assert set(result) == {"total", "synced", "skipped", "last_hero_id"}
    assert result["synced"] == len(MATCHUPS)
    assert result["skipped"] == 0
    assert result["last_hero_id"] == max(MATCHUPS)
    expected_rows = sum(
        1 for pairs in MATCHUPS.values()
        for _against, games, _wins in pairs if games >= 100
    )
    assert result["total"] == expected_rows == 11
    _, sessionmaker = db
    with sessionmaker() as session:
        rows = CounterRepository(session).get_hero_counters(1)
    assert {(h.id, wr, sample) for h, wr, sample in rows} == {
        (2, 52.0, 5000), (3, round(140 / 300 * 100, 2), 300)}
    with sessionmaker() as session:
        raw = SettingsRepository(session).get("matchups_synced_hero_ids")
    assert json.loads(raw) == [1, 2, 3, 4]  # прогресс обновлён после успеха


def test_sync_matchups_all_resume_after_failure(db) -> None:
    """Сбой героя -> resume продолжает: уже сделанные не перезапрашиваются."""
    calls: list[int] = []
    _seed_heroes(db)
    client = _mk_client(db, call_fail_hero=2)
    first = client.sync_matchups_all()
    assert first["skipped"] == 1 and first["synced"] == len(MATCHUPS) - 1
    assert first["last_hero_id"] == 4  # последний успешный
    _, sessionmaker = db
    with sessionmaker() as session:
        raw = SettingsRepository(session).get("matchups_synced_hero_ids")
    assert set(json.loads(raw)) == {1, 3, 4}  # герой 2 не отмечен

    def counting_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if "/matchups" in path:
            calls.append(int(path.split("/")[-2]))
        return httpx.Response(200, json=[
            {"hero_id": 2, "against_hero_id": 1,
             "games_played": 500, "wins": 240}])

    engine, sessionmaker2 = db
    client2 = OpenDotaClient(
        settings=_fast_settings(), validator=ValidatorService(),
        engine=engine, sessionmaker=sessionmaker2,
        http_client=httpx.Client(
            transport=httpx.MockTransport(counting_handler)))
    client2.retry_delays = (0.0, 0.0, 0.0)
    second = client2.sync_matchups_all()  # resume=True по умолчанию
    assert calls == [2]  # докрутили только сломанного
    assert second["synced"] == 1 and second["skipped"] == 0
    assert second["last_hero_id"] == 2


def test_sync_matchups_all_min_games_filter(db) -> None:
    """min_games: пары с меньшей выборкой не пишутся вовсе."""
    _seed_heroes(db)
    client = _mk_client(db)
    result = client.sync_matchups_all(min_games=500)
    # games >= 500: пара 1->2 и 2->1
    assert result["total"] == 2
    _, sessionmaker = db
    with sessionmaker() as session:
        top = CounterRepository(session).top_advantages(1, limit=5)
    assert [h.id for h, _win in top] == [2]


def test_top_advantages_and_disadvantages(db) -> None:
    """top_advantages — кого контрит; top_disadvantages — кто контрит."""
    _seed_heroes(db)
    client = _mk_client(db)
    client.sync_matchups_all(resume=True)
    _, sessionmaker = db
    with sessionmaker() as session:
        repo = CounterRepository(session)
        adv = repo.top_advantages(1, limit=5)
        dis = repo.top_disadvantages(1, limit=5)
    # (1 -> 2, 52.0), (1 -> 3, 46.67): пара с games=80 отфильтрована
    assert [(h.id, w) for h, w in adv] == [(2, 52.0), (3, round(140 / 300 * 100, 2))]
    # Кто контрит 1: (2 -> 1, 48.0), (3 -> 1, 53.33), (4 -> 1, 52.0)
    assert {(h.id, w) for h, w in dis} == {
        (2, 48.0), (3, round(160 / 300 * 100, 2)), (4, 52.0)}


def test_sync_matchups_all_empty_db(db) -> None:
    """Пустая БД героев -> нулевой результат без исключений."""
    client = _mk_client(db)
    assert client.sync_matchups_all() == {
        "total": 0, "synced": 0, "skipped": 0, "last_hero_id": None}
