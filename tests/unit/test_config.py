"""Тесты конфигурации Settings (T-002)."""

from vetmo.infra.config import Settings


def _make_settings() -> Settings:
    return Settings(_env_file=None)


def test_settings_loads_without_env_file() -> None:
    """Настройки загружаются без .env файла и секретов (по умолчанию None)."""
    s = _make_settings()
    assert s.app_name == "vetmo"
    assert s.supabase_url is None
    assert s.supabase_key is None


def test_settings_defaults() -> None:
    """Проверка значений по умолчанию всех полей."""
    s = _make_settings()
    assert s.log_level == "INFO"
    assert s.db_url == "sqlite:///vetmo.db"
    assert s.log_file == "logs/vetmo.log"
    assert s.http_timeout == 15.0
    assert s.opendota_base_url == "https://api.opendota.com/api/"
    assert s.rate_limit_per_min == 60
    assert s.cache_ttl_hours == 24.0


def test_settings_reads_env_prefix() -> None:
    """С переменных окружения с префиксом VETMO_ читается значение."""
    s = Settings(_env_file=None, log_level="DEBUG")
    assert s.log_level == "DEBUG"


def test_settings_extra_ignored() -> None:
    """Лишние переменные окружения не вызывают ошибку."""
    s = Settings(_env_file=None, unknown_var="x")
    assert s.app_name == "vetmo"
