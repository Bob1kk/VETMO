"""Конфигурация приложения (pydantic-settings, .env). Публичный контракт T-002."""

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from vetmo.infra.public_config import public_supabase_defaults


def _env_files() -> tuple[str, ...]:
    """``.env`` рядом с проектом, в ``%APPDATA%/VETMO`` и рядом с exe."""
    files = [".env"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        files.append(str(Path(appdata) / "VETMO" / ".env"))
    if getattr(sys, "frozen", False):
        files.append(str(Path(sys.executable).resolve().parent / ".env"))
    return tuple(files)


def _default_log_file() -> str:
    """В exe пишем логи в %APPDATA%/VETMO, в dev — в logs/ проекта."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return str(Path(appdata) / "VETMO" / "logs" / "vetmo.log")
    return "logs/vetmo.log"


class Settings(BaseSettings):
    """Настройки приложения, читаются из окружения с префиксом VETMO_."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        env_prefix="VETMO_",
        extra="ignore",
    )

    app_name: str = "vetmo"
    # Публичные URL/anon-ключ вшиваются только в exe (см. public_config.py).
    supabase_url: str | None = Field(
        default_factory=lambda: public_supabase_defaults()[0]
    )
    supabase_anon_key: str | None = Field(
        default_factory=lambda: public_supabase_defaults()[1]
    )
    # Legacy alias; new code uses supabase_anon_key.
    supabase_key: str | None = None
    log_level: str = "INFO"
    db_url: str = "sqlite:///vetmo.db"
    log_file: str = Field(default_factory=_default_log_file)
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
