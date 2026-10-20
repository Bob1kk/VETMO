"""Настройки sync-скрипта: service_role и STRATZ token.

Эти значения НЕ читаются приложением и НЕ попадают в exe.
Файл по умолчанию: %APPDATA%/VETMO/secrets.env (вне OneDrive).
Можно переопределить через VETMO_SYNC_SECRETS_FILE.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


def default_secrets_path() -> Path:
    """Путь к локальному файлу секретов sync-скрипта."""
    override = os.environ.get("VETMO_SYNC_SECRETS_FILE")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "VETMO" / "secrets.env"


@dataclass(slots=True)
class SyncSettings:
    """Параметры записи в Supabase и доступа к STRATZ."""

    supabase_url: str
    service_key: str
    stratz_token: str
    stratz_api_url: str = "https://api.stratz.com/graphql"
    secrets_file: Path = field(default_factory=default_secrets_path)

    @classmethod
    def load(cls) -> SyncSettings:
        """Читает секреты из файла и переменных окружения.

        Приоритет: переменные окружения > файл секретов.
        """
        path = default_secrets_path()
        file_values = dotenv_values(path) if path.is_file() else {}

        def pick(name: str) -> str:
            value = os.environ.get(name) or file_values.get(name) or ""
            return str(value).strip()

        url = pick("VETMO_SYNC_SUPABASE_URL") or pick("VETMO_SUPABASE_URL")
        service = pick("VETMO_SYNC_SERVICE_KEY")
        token = pick("VETMO_SYNC_STRATZ_TOKEN")
        if not url:
            raise RuntimeError(
                "Не задан VETMO_SYNC_SUPABASE_URL. "
                f"Ожидался файл {path} или переменная окружения."
            )
        if not service:
            raise RuntimeError(
                "Не задан VETMO_SYNC_SERVICE_KEY. "
                "service_role нельзя хранить в репозитории или exe."
            )
        if not token:
            raise RuntimeError("Не задан VETMO_SYNC_STRATZ_TOKEN.")
        # URL без /rest/v1 — supabase-py ожидает базовый адрес.
        url = url.split("/rest/v1")[0].rstrip("/")
        return cls(
            supabase_url=url,
            service_key=service,
            stratz_token=token,
            secrets_file=path,
        )
