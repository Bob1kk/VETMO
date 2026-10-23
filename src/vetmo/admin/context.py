"""Контекст VETMO Admin: секреты, STRATZ-клиент и Supabase service_role.

Создаётся один раз при старте Admin-программы. Секреты читаются из
``%APPDATA%/VETMO/secrets.env`` (или ``VETMO_SYNC_SECRETS_FILE``) и никогда
не логируются.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vetmo.admin.repository import AdminRepository
from vetmo.infra.config import Settings
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.infra.sync_settings import SyncSettings, default_secrets_path
from vetmo.services.stratz_client import StratzClient


def _service_gateway(sync: SyncSettings) -> SupabaseGateway:
    """Gateway с ``service_role``: обходит RLS, поэтому только для Admin."""
    settings = Settings(
        supabase_url=sync.supabase_url,
        supabase_anon_key=sync.service_key,
    )
    return SupabaseGateway(settings)


@dataclass
class AdminContext:
    """Общие зависимости Admin-приложения."""

    sync: SyncSettings
    client: StratzClient
    gateway: SupabaseGateway
    repository: AdminRepository
    secrets_path: Path

    def close(self) -> None:
        """Закрывает сетевые клиенты; безопасно вызывать повторно."""
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - выход не должен падать из-за сети
            pass
        try:
            self.gateway.close()
        except Exception:  # noqa: BLE001
            pass


def create_admin_context() -> AdminContext:
    """Загружает секреты и собирает ``AdminContext``.

    Raises:
        RuntimeError: если файл секретов отсутствует или в нём нет
            ``VETMO_SYNC_SUPABASE_URL`` / ``VETMO_SYNC_SERVICE_KEY`` /
            ``VETMO_SYNC_STRATZ_TOKEN``. Сообщение содержит путь к файлу.
    """
    secrets_path = default_secrets_path()
    try:
        sync = SyncSettings.load()
    except RuntimeError as exc:
        raise RuntimeError(
            "Не удалось загрузить секреты VETMO Admin.\n"
            f"Файл: {secrets_path}\n"
            "Нужны переменные VETMO_SYNC_SUPABASE_URL, VETMO_SYNC_SERVICE_KEY "
            "и VETMO_SYNC_STRATZ_TOKEN.\n"
            f"Причина: {exc}"
        ) from exc

    client = StratzClient(sync.stratz_token, url=sync.stratz_api_url)
    try:
        gateway = _service_gateway(sync)
        repository = AdminRepository(gateway)
    except Exception:
        client.close()
        raise

    return AdminContext(
        sync=sync,
        client=client,
        gateway=gateway,
        repository=repository,
        secrets_path=getattr(sync, "secrets_file", secrets_path),
    )


__all__ = ["AdminContext", "create_admin_context"]
