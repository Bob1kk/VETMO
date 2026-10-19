"""Тесты SupabaseClient stub (T-016): без учётных данных — no-op без исключений."""

from vetmo.infra.config import Settings
from vetmo.infra.supabase_stub import SupabaseClient


def test_no_credentials_noop() -> None:
    """Без SUPABASE_URL/KEY -> enabled=False, sent=0, без исключений."""
    settings = Settings(_env_file=None)  # supabase_url/key = None
    client = SupabaseClient(settings)
    result = client.sync_meta_snapshot()
    assert result == {"enabled": False, "sent": 0}


def test_no_credentials_with_real_sessionmaker(db) -> None:
    """Даже с БД: нет учётных данных -> no-op."""
    _, sessionmaker = db
    settings = Settings(_env_file=None)
    client = SupabaseClient(settings, sessionmaker=sessionmaker)
    assert client.sync_meta_snapshot()["enabled"] is False


def test_with_credentials_service_marks_enabled(db, monkeypatch) -> None:
    """С учётными данными: enabled=True; слияние ошибки сети не роняет."""
    _, sessionmaker = db
    settings = Settings(_env_file=None)
    settings = settings.model_copy(update={
        "supabase_url": "https://example.supabase.co",
        "supabase_key": "test-key",
    })
    client = SupabaseClient(settings, sessionmaker=sessionmaker)
    # http_client с транспортом, бросающим исключение — best-effort, не падает.
    import httpx

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client._http = httpx.Client(transport=httpx.MockTransport(broken))  # noqa: SLF001
    result = client.sync_meta_snapshot()
    assert result["enabled"] is True
    assert result["sent"] == 0  # ошибка проглочена
