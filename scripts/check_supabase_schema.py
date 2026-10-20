"""Проверка наличия таблиц/views VETMO в Supabase.

Печатает только имена и статусы. Ключи не выводятся.
Запуск: .\\.venv\\Scripts\\python.exe scripts\\check_supabase_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = [
    "vetmo_heroes",
    "vetmo_patches",
    "vetmo_meta",
    "vetmo_snapshots",
    "vetmo_hero_matchups",
    "vetmo_news",
    "vetmo_profiles",
    "vetmo_drafts",
    "vetmo_draft_picks",
    "vetmo_sync_runs",
]
EXPECTED_VIEWS = ["v_vetmo_meta", "v_vetmo_sync_status"]


def _env() -> dict[str, str]:
    values = dotenv_values(ROOT / ".env") if (ROOT / ".env").is_file() else {}
    secrets_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "VETMO" / "secrets.env"
    if secrets_path.is_file():
        values.update(dotenv_values(secrets_path))
    values.update({k: v for k, v in os.environ.items() if k.startswith("VETMO_")})
    return {str(k): str(v) for k, v in values.items() if v is not None}


def main() -> int:
    values = _env()
    url = (values.get("VETMO_SYNC_SUPABASE_URL") or values.get("VETMO_SUPABASE_URL") or "").rstrip("/")
    key = values.get("VETMO_SYNC_SERVICE_KEY") or values.get("VETMO_SUPABASE_ANON_KEY") or ""
    if not url or not key:
        print("Нет URL или ключа Supabase (.env / secrets.env).")
        return 2
    url = url.split("/rest/v1")[0].rstrip("/")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url + "/rest/v1/", headers=headers)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка сети: {type(exc).__name__}")
        return 3
    if response.status_code != 200:
        print(f"Supabase вернул HTTP {response.status_code}; ключ/URL проверить.")
        return 4
    paths = set(response.json().get("paths", {}))
    missing = 0
    for table in EXPECTED_TABLES + EXPECTED_VIEWS:
        present = f"/{table}" in paths
        print(f"{'OK ' if present else 'MISS'} {table}")
        if not present:
            missing += 1
    if missing:
        print(f"\nНе найдено объектов: {missing}. Примените supabase/migrations/20261020_001_init.sql.")
        return 1
    print("\nВсе объекты VETMO на месте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
