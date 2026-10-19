"""Централизованная сборка http-клиента (с системным прокси Windows).

Бетовый нюанс: при включённом системном прокси (v2rayN/Clash на 127.0.0.1:…)
прямые запросы к api.opendota.com «висят» — httpx должен ходить через прокси,
как это делает PowerShell/.NET. Фабрика `build_http_client` решает это в одном
месте для всех потребителей (OpenDotaClient, NewsService, SupabaseClient, CV).
"""

from __future__ import annotations

import httpx

from vetmo.infra.proxy import system_proxy_url


def build_http_client(
    timeout: float | httpx.Timeout = 45.0, follow_redirects: bool = True,
) -> httpx.Client:
    """httpx.Client с системным прокси (если он есть) и заданным таймаутом."""
    proxy = system_proxy_url()
    kwargs: dict = {"timeout": timeout, "follow_redirects": follow_redirects}
    if proxy:
        kwargs["proxy"] = proxy
        kwargs["trust_env"] = True
    return httpx.Client(**kwargs)
