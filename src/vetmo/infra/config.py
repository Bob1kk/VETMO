"""Конфигурация приложения (pydantic-settings, .env). Публичный контракт T-002."""

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """``.env`` рядом с проектом, в ``%APPDATA%/VETMO`` и рядом с exe."""
    files = [".env"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        files.append(str(Path(appdata) / "VETMO" / ".env"))
    if getattr(sys, "frozen", False):
        files.append(str(Path(sys.executable).resolve().parent / ".env"))
    return tuple(files)


class Settings(BaseSettings):
    """Настройки приложения, читаются из окружения с префиксом VETMO_."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        env_prefix="VETMO_",
        extra="ignore",
    )

    app_name: str = "vetmo"
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    # Legacy alias; new code uses supabase_anon_key.
    supabase_key: str | None = None
    log_level: str = "INFO"
    db_url: str = "sqlite:///vetmo.db"
    log_file: str = "logs/vetmo.log"
    http_timeout: float = 45.0
    opendota_base_url: str = "https://api.opendota.com/api/"
    rate_limit_per_min: int = 60
    cache_ttl_hours: float = 24.0
    news_ttl_hours: float = 1.0
    meta_window_days: int = 7
    position_min_share: float = 25.0
    position_min_matches: int = 500
    meta_refresh_minutes: int = 30

    @property
    def supabase_publishable_key(self) -> str | None:
        """Публичный ключ приложения (anon/publishable)."""
        return self.supabase_anon_key or self.supabase_key
