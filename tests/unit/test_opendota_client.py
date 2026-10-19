"""Тесты OpenDotaClient (T-008): rate limit, дедуп, ошибка сети не роняет."""

from datetime import UTC, datetime, timedelta

import httpx

from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.infra.config import Settings
from vetmo.services.opendota_client import OpenDotaClient, SyncResult
from vetmo.services.validator_service import ValidatorService

HERO_STATS = [
    {
        "id": 1, "name": "npc_dota_hero_antimage", "localized_name": "Anti-Mage",
        "primary_attr": "agi", "attack_type": "Melee",
        "roles": ["Carry", "Escape"], "icon": "//cdn.opendota.com/x1.png",
    },
    {
        "id": 2, "name": "npc_dota_hero_axe", "localized_name": "Axe",
        "primary_attr": "str", "attack_type": "Melee", "roles": ["Initiator"],
        "img": "https://cdn.opendota.com/x2.png",
    },
]


def _fast_settings() -> Settings:
    """Без .env; интервал лимита 60/1200 = 0.05с — быстро для тестов."""
    return Settings(_env_file=None, rate_limit_per_min=1200)


def _mk_client(db, handler, settings=None) -> OpenDotaClient:
    """Клиент поверх временной БД с mock-транспортом и без задержек ретраев."""
    engine, sessionmaker = db
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        settings=settings or _fast_settings(),
        validator=ValidatorService(),
        engine=engine, sessionmaker=sessionmaker,
        http_client=http_client,
    )
    client.retry_delays = (0.0, 0.0, 0.0)
    return client


def test_sync_heroes_parses_and_saves(db) -> None:
    """heroStats маппится; icon '//cdn' -> 'https://cdn'."""
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=HERO_STATS)

    client = _mk_client(db, ok)
    result = client.sync_heroes()
    assert result.ok == 2 and result.quarantined == 0
    _, sessionmaker = db
    with sessionmaker() as session:
        heroes = HeroRepository(session).get_all()
    assert len(heroes) == 2
    am = next(h for h in heroes if h.id == 1)
    assert am.icon_url == "https://cdn.opendota.com/x1.png"
    assert am.roles == ["Carry", "Escape"]
    axe = next(h for h in heroes if h.id == 2)
    assert axe.icon_url == "https://cdn.opendota.com/x2.png"
    assert axe.localized_name == "Axe"


def test_sync_heroes_dedup_on_resync(db) -> None:
    """Повторный sync не создаёт дублей (Review Focus #3), кэш не даёт сеть."""
    calls = []

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=HERO_STATS)

    client = _mk_client(db, ok)
    assert client.sync_heroes().ok == 2
    second = client.sync_heroes()  # свежий кэш: сеть не трогается
    assert len(calls) == 1
    assert isinstance(second, SyncResult) and second.ok == 2
    _, sessionmaker = db
    with sessionmaker() as session:
        assert HeroRepository(session).count() == 2


def test_sync_heroes_quarantines_invalid(db) -> None:
    """Невалидный герой (пустое имя) карантинится и не сохраняется."""
    data = [*HERO_STATS, {"id": 99, "name": "", "localized_name": " "}]

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    client = _mk_client(db, ok)
    result = client.sync_heroes()
    assert result.quarantined == 1 and result.ok == 2
    _, sessionmaker = db
    with sessionmaker() as session:
        assert HeroRepository(session).count() == 2


def test_network_error_no_exception(db) -> None:
    """Сетевая ошибка -> SyncResult со skipped > 0, БД не тронута."""
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = _mk_client(db, broken)
    result = client.sync_heroes()
    assert result.ok == 0 and result.skipped > 0
    _, sessionmaker = db
    with sessionmaker() as session:
        assert HeroRepository(session).count() == 0


def test_server_error_retries_3_times(db) -> None:
    """5xx: ровно 3 попытки ретрая, затем graceful skip."""
    calls = []

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="busy")

    client = _mk_client(db, fail)
    result = client.sync_heroes()
    assert len(calls) == 3
    assert result.ok == 0 and result.skipped > 0


def test_cache_prevents_network_within_ttl(db) -> None:
    """Свежий last_sync_heroes -> сеть не вызывается."""
    calls = []

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=HERO_STATS)

    client = _mk_client(db, ok)
    client.sync_heroes()
    second = client.sync_heroes()
    assert len(calls) == 1
    assert second.ok == 2


def test_stale_cache_allows_network(db) -> None:
    """Кэш старше cache_ttl_hours -> сеть вызывается заново."""
    calls = []

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=HERO_STATS)

    client = _mk_client(db, ok)
    client.sync_heroes()
    _, sessionmaker = db
    stale = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with sessionmaker() as session:
        SettingsRepository(session).set("last_sync_heroes", stale)
    assert client.sync_heroes().ok == 2
    assert len(calls) == 2


def test_rate_limit_between_consecutive_requests(db) -> None:
    """Интервал между запросами >= 60/rate_limit_per_min секунд."""
    import time

    stamps: list[float] = []

    def ok(request: httpx.Request) -> httpx.Response:
        stamps.append(time.perf_counter())
        return httpx.Response(200, json=[])

    settings = Settings(_env_file=None, rate_limit_per_min=1200)  # 0.05с
    client = _mk_client(db, ok, settings=settings)
    client._request("heroStats")
    client._request("heroStats")
    assert len(stamps) == 2
    # 0.05с интервал; допуск 0.005 на таймеры Windows
    assert (stamps[1] - stamps[0]) >= 0.045


def test_sync_matchups_saves_counters_dedup(db) -> None:
    """matchups -> CounterRepository; win_rate_against = wins/games*100; дедуп."""
    def ok(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heroStats"):
            return httpx.Response(200, json=HERO_STATS)
        if request.url.path.endswith("/heroes/1/matchups"):
            return httpx.Response(200, json=[
                {"hero_id": 1, "against_hero_id": 2,
                 "games_played": 100, "wins": 55},
            ])
        return httpx.Response(200, json=[])

    client = _mk_client(db, ok)
    client.sync_heroes()
    # Двa вызова: дедуп по паре не размножает строки
    assert client.sync_matchups(hero_ids=[1], rivals_per_hero=5).ok == 1
    assert client.sync_matchups(hero_ids=[1], rivals_per_hero=5).ok == 1
    _, sessionmaker = db
    with sessionmaker() as session:
        counters = CounterRepository(session).get_hero_counters(1)
    assert len(counters) == 1
    assert {hero.id: wr for hero, wr, _ in counters} == {2: 55.0}


def test_sync_matchups_partial_failure(db) -> None:
    """Сеть легла на одного героя — остальные ок, skipped, без исключений."""
    def ok(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heroes/1/matchups"):
            raise httpx.ConnectError("boom")
        if request.url.path.endswith("/heroStats"):
            return httpx.Response(200, json=HERO_STATS)
        return httpx.Response(200, json=[
            {"hero_id": 2, "against_hero_id": 1,
             "games_played": 10, "wins": 6},
        ])

    client = _mk_client(db, ok)
    client.sync_heroes()
    result = client.sync_matchups(hero_ids=[1, 2], rivals_per_hero=5)
    assert result.skipped == 1 and result.ok == 1
