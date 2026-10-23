r"""CLI sync OpenDota heroStats -> Supabase (main meta).

Запуск:
    .\.venv\Scripts\python.exe tools\sync_opendota.py --dry-run
    .\.venv\Scripts\python.exe tools\sync_opendota.py

Отвечает за:
  * ветеринарный каталог героев (vetmo_heroes)
  * патчи (vetmo_patches)
  * основную мету — win_rate, pick_rate, ban_rate (vetmo_meta)

OpenDota не требует токена API. Настройки берутся из
%APPDATA%\VETMO\secrets.env (или переменных окружения VETMO_SYNC_*).

Приложение никогда не получает service_role: запись выполняет только этот
скрипт. Пользовательское приложение читает уже агрегированные строки через
anon-ключ Supabase.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from vetmo.services.stratz_sync import sync_opendota_meta  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VETMO OpenDota sync (main meta)")
    parser.add_argument("--dry-run", action="store_true",
                        help="прочитать OpenDota, не писать в Supabase")
    parser.add_argument("--trigger", default="manual",
                        help="источник запуска sync")
    parser.add_argument("--request-id", default=None,
                        help="идентификатор прогона для трассировки")
    parser.add_argument("--json", action="store_true",
                        help="вывести итог в формате JSON в stdout")
    args = parser.parse_args(argv)

    try:
        result = sync_opendota_meta(
            dry_run=args.dry_run,
            trigger=args.trigger,
            request_id=args.request_id,
        )
    except Exception as exc:  # noqa: BLE001
        message = f"SYNC FAILED: {type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({
                "source": "opendota",
                "status": "error",
                "errors": [message],
                "trigger": args.trigger,
                "request_id": args.request_id,
            }, ensure_ascii=False))
        else:
            print(message)
        return 1

    if args.json:
        print(json.dumps({
            "source": result.source,
            "patch_version": result.patch_version,
            "patch_id": result.patch_id,
            "rows_meta": result.rows_meta,
            "errors": result.errors,
            "trigger": args.trigger,
            "request_id": args.request_id,
        }, ensure_ascii=False))
    else:
        print("\nИтог OpenDota sync:")
        print(f"  источник: {result.source}")
        print(f"  патч: {result.patch_version} (id {result.patch_id})")
        print(f"  мета-строк: {result.rows_meta}")
        if result.errors:
            print(f"  ошибок: {len(result.errors)}")
            for error in result.errors[:10]:
                print(f"    - {error}")
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
