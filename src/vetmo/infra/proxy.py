"""Определение системного прокси Windows (нюанс beta-запуска).

На машинах с локальным туннелем (v2rayN/Clash: 127.0.0.1:10809 и т.п.) системные
клиенты ходят через прокси, а Python-стек по умолчанию — напрямую и «виснет» на
заблокированных хостах (OpenDota). Читаем реестр как это делает .NET.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

ENV_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")


def _proxy_from_registry() -> str | None:
    """ProxyEnable/ProxyServer из HKCU (как у PowerShell/.NET). None если выключено."""
    try:
        import winreg  # noqa: PLC0415 — импорт только на Windows

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not enabled:
                return None
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except (ImportError, FileNotFoundError, OSError):
        return None
    if not server:
        return None
    # ProxyServer бывает "127.0.0.1:10809" или "http=...;https=...;ftp=..."
    if "=" in server:
        parts = dict(p.split("=", 1) if "=" in p else ("*", p) for p in server.split(";"))
        server = parts.get("https") or parts.get("http") or parts.get("*")
    if not server:
        return None
    if "://" not in server:
        server = "http://" + server
    return server


def system_proxy_url() -> str | None:
    """Прокси-URL: явные переменные окружения > реестр Windows. None при их отсутствии."""
    for var in ENV_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return _proxy_from_registry()
