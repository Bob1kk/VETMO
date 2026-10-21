"""Public Supabase defaults are embedded only in frozen user builds."""

import sys
from pathlib import Path

from vetmo.infra.config import Settings
from vetmo.infra.public_config import PUBLIC_SUPABASE_ANON_KEY, PUBLIC_SUPABASE_URL


def test_source_mode_does_not_use_public_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.supabase_url is None
    assert settings.supabase_anon_key is None


def test_frozen_mode_uses_public_supabase_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    settings = Settings(_env_file=None)
    assert settings.supabase_url == PUBLIC_SUPABASE_URL
    assert settings.supabase_publishable_key == PUBLIC_SUPABASE_ANON_KEY


def test_frozen_mode_writes_logs_to_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.log_file == str(tmp_path / "VETMO" / "logs" / "vetmo.log")
