"""Конфигурация приложения (pydantic-settings, .env). Публичный контракт T-002."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, читаются из окружения с префиксом VETMO_."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VETMO_",
        extra="ignore",
    )

    app_name: str = "vetmo"
    supabase_url: str | None = None
    supabase_key: str | None = None
    log_level: str = "INFO"
    db_url: str = "sqlite:///vetmo.db"
    log_file: str = "logs/vetmo.log"
    http_timeout: float = 15.0
    opendota_base_url: str = "https://api.opendota.com/api/"
    rate_limit_per_min: int = 60
    cache_ttl_hours: float = 24.0
