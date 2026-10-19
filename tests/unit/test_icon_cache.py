"""R2-тесты sync_icon_cache: скачивание в tmp, кэш, сбой сети не крашит."""

import httpx

from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.services.opendota_client import OpenDotaClient
from vetmo.services.validator_service import ValidatorService

PNG = b"\x89PNG\r\n\x1a\nfake-bytes"


def _fast_settings() -> Settings:
    return Settings(_env_file=None, rate_limit_per_min=1200)


def _mk_client(db, handler) -> OpenDotaClient:
    engine, sessionmaker = db
    client = OpenDotaClient(
        settings=_fast_settings(), validator=ValidatorService(),
        engine=engine, sessionmaker=sessionmaker,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.retry_delays = (0.0, 0.0, 0.0)
    return client


def _seed(db) -> None:
    _, sessionmaker = db
    with sessionmaker() as session:
        repo = HeroRepository(session)
        for hero in (
            Hero(id=1, name="h1", localized_name="H1", primary_attr="str",
                 attack_type="Melee", roles=[],
                 icon_url="https://cdn.test/1.png"),
            Hero(id=2, name="h2", localized_name="H2", primary_attr="str",
                 attack_type="Melee", roles=[],
                 icon_url="https://cdn.test/2.png"),
            Hero(id=3, name="h3", localized_name="H3", primary_attr="str",
                 attack_type="Melee", roles=[], icon_url=None),  # без url
        ):
            repo.upsert(hero)


def _mock(handler) -> httpx.Client:
    """Mock-клиент для передачи в sync_icon_cache(http_client=...)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_saves_files(db, tmp_path) -> None:
    """Иконки скачиваются в icons_dir/{hero_id}.png с корректным байтом."""
    _seed(db)
    icons = tmp_path / "icons"

    def ok(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "cdn.test"
        return httpx.Response(200, content=PNG)

    client = _mk_client(db, ok)
    result = client.sync_icon_cache(icons_dir=icons, http_client=_mock(ok))
    assert result == {"downloaded": 2, "cached": 0, "failed": 1}  # h3 без url
    assert (icons / "1.png").read_bytes() == PNG
    assert (icons / "2.png").stat().st_size > 0
    assert not (icons / "3.png").exists()


def test_caches_existing_nonempty_files(db, tmp_path) -> None:
    """Непустой существующий файл -> cached; 0-байт -> перекачивается."""
    _seed(db)
    icons = tmp_path / "icons"
    icons.mkdir()
    (icons / "1.png").write_bytes(PNG)          # полноценный кэш
    (icons / "2.png").write_bytes(b"")          # битый (0 байт) -> заново
    calls: list[str] = []

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, content=PNG)

    client = _mk_client(db, ok)
    result = client.sync_icon_cache(
        icons_dir=icons, http_client=_mock(ok))  # h1 cached, h2 докачан
    assert result == {"downloaded": 1, "cached": 1, "failed": 1}
    assert calls == ["/2.png"]                  # 1.png не перекачан


def test_http_error_counts_failed_no_crash(db, tmp_path) -> None:
    """HTTP 500/404 и сетевой сбой -> failed, без исключений."""
    _seed(db)
    icons = tmp_path / "icons"

    def fail(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/1.png":
            raise httpx.ConnectError("no route")
        return httpx.Response(404, text="gone")

    client = _mk_client(db, fail)
    result = client.sync_icon_cache(
        icons_dir=icons, http_client=_mock(fail))
    assert result["downloaded"] == 0
    assert result["failed"] == 3
