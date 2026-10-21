"""Публичные параметры Supabase для пользовательской сборки.

URL проекта и publishable/anon-ключ не являются секретами: такой ключ
предназначен для распространения в клиентских приложениях, а доступ к данным
ограничен RLS. service_role и токены STRATZ сюда не попадают — они читаются
только Admin/sync-скриптом из ``%APPDATA%/VETMO/secrets.env``.

Значения применяются только в собранном exe (``sys.frozen``): запуск из
исходников продолжает брать настройки из локального ``.env``.
"""

from __future__ import annotations

import sys

PUBLIC_SUPABASE_URL = "https://qtqntybxwwhggqimkxpi.supabase.co"
PUBLIC_SUPABASE_ANON_KEY = "sb_publishable_tbUGnJBg8Pyjd-8KstlEyQ_aLVHW7JU"


def public_supabase_defaults() -> tuple[str | None, str | None]:
    """Публичные URL/ключ для frozen-сборки, иначе (None, None)."""
    if not getattr(sys, "frozen", False):
        return None, None
    return PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY
