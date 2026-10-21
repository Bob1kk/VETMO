"""Тесты ``AdminContext`` (T-112): загрузка секретов и отсутствие ключей.

Реальные ``secrets.env`` и сеть не используются: путь подменяется временным
файлом, а в нём лежат только фиктивные значения.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vetmo.admin.context import create_admin_context
from vetmo.infra.sync_settings import SyncSettings

SECRET_ENV_VARS = (
    "VETMO_SYNC_SUPABASE_URL",
    "VETMO_SYNC_SERVICE_KEY",
    "VETMO_SYNC_STRATZ_TOKEN",
    "VETMO_SUPABASE_URL",
    "VETMO_SYNC_SECRETS_FILE",
)


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Убирает реальные переменные и направляет загрузку во временный файл."""
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    secrets = tmp_path / "secrets.env"
    monkeypatch.setenv("VETMO_SYNC_SECRETS_FILE", str(secrets))
    return secrets


def test_create_admin_context_reports_missing_secrets_file(
    clean_env: Path,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        create_admin_context()

    message = str(excinfo.value)
    assert str(clean_env) in message
    assert "VETMO_SYNC_SERVICE_KEY" in message
    assert "VETMO_SYNC_STRATZ_TOKEN" in message


def test_create_admin_context_reports_missing_service_key(
    clean_env: Path,
) -> None:
    clean_env.write_text(
        "VETMO_SYNC_SUPABASE_URL=https://example.supabase.co\n"
        "VETMO_SYNC_STRATZ_TOKEN=fake-stratz-token\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="VETMO_SYNC_SERVICE_KEY"):
        create_admin_context()


def test_create_admin_context_reads_secrets_and_builds_services(
    clean_env: Path,
) -> None:
    clean_env.write_text(
        "VETMO_SYNC_SUPABASE_URL=https://example.supabase.co/rest/v1\n"
        "VETMO_SYNC_SERVICE_KEY=fake-service-key\n"
        "VETMO_SYNC_STRATZ_TOKEN=fake-stratz-token\n",
        encoding="utf-8",
    )

    context = create_admin_context()
    try:
        assert context.sync.supabase_url == "https://example.supabase.co"
        assert context.sync.service_key == "fake-service-key"
        assert context.sync.stratz_token == "fake-stratz-token"
        assert context.secrets_path == clean_env
        assert context.gateway.is_configured
        assert context.repository.gateway is context.gateway
    finally:
        context.close()


def test_sync_settings_env_overrides_file(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env.write_text(
        "VETMO_SYNC_SUPABASE_URL=https://file.supabase.co\n"
        "VETMO_SYNC_SERVICE_KEY=file-key\n"
        "VETMO_SYNC_STRATZ_TOKEN=file-token\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VETMO_SYNC_SERVICE_KEY", "env-key")

    settings = SyncSettings.load()

    assert settings.supabase_url == "https://file.supabase.co"
    assert settings.service_key == "env-key"
    assert settings.stratz_token == "file-token"
