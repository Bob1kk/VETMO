"""CLI sync STRATZ -> Supabase.

Примеры:
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --dry-run --no-matchups
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --no-matchups
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py
    .\\.venv\\Scripts\\python.exe tools\\sync_stratz.py --trigger workflow_dispatch --request-id <id> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from vetmo.services.stratz_sync import sync_all  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VETMO STRATZ sync")
    parser.add_argument("--dry-run", action="store_true",
                        help="только прочитать STRATZ, не писать в Supabase")
    parser.add_argument("--no-matchups", action="store_true",
                        help="не синхронизировать матчапы (5 запросов по ранговым срезам)")
    parser.add_argument("--ranks", default="0-8",
                        help="диапазон рангов, например 0-8 или 0,8")
    parser.add_argument("--positions", default="0-5",
                        help="диапазон позиций, например 0-5 или 0,1")
    parser.add_argument("--trigger", default="manual",
                        help="источник запуска sync (например workflow_dispatch, manual)")
    parser.add_argument("--request-id", default=None,
                        help="идентификатор запроса/прогона для сквозной трассировки")
    parser.add_argument("--json", action="store_true",
                        help="вывести итог в формате JSON в stdout")
    args = parser.parse_args(argv)

    def parse_range(value: str) -> range:
        if "," in value:
            items = sorted({int(item) for item in value.split(",") if item.strip()})
            if not items:
                raise ValueError("пустой диапазон")
            return range(items[0], items[-1] + 1)
        if "-" in value:
            start, end = value.split("-", 1)
            return range(int(start), int(end) + 1)
        number = int(value)
        return range(number, number + 1)

    try:
        ranks = parse_range(args.ranks)
        positions = parse_range(args.positions)
    except ValueError as exc:
        print(f"Неверный диапазон: {exc}")
        return 2

    try:
        stats = sync_all(
            dry_run=args.dry_run,
            include_matchups=not args.no_matchups,
            ranks=ranks,
            positions=positions,
        )
    except Exception as exc:  # noqa: BLE001 - CLI должен показать причину
        message = f"SYNC FAILED: {type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({
                "patch_id": None,
                "patch_version": None,
                "rows_meta": 0,
                "rows_matchups": 0,
                "status": "error",
                "errors": [message],
                "trigger": args.trigger,
                "request_id": args.request_id,
            }, ensure_ascii=False))
        else:
            print(message)
        return 1

    status = "partial" if stats.errors else "ok"

    if args.json:
        print(json.dumps({
            "patch_id": stats.patch_id,
            "patch_version": stats.patch_version,
            "rows_meta": stats.rows_meta,
            "rows_matchups": stats.rows_matchups,
            "status": status,
            "errors": stats.errors,
            "trigger": args.trigger,
            "request_id": args.request_id,
        }, ensure_ascii=False))
    else:
        print("\nИтог:")
        print(f"  патч: {stats.patch_version} (id {stats.patch_id})")
        print(f"  триггер: {args.trigger}"
              + (f", request-id: {args.request_id}" if args.request_id else ""))
        print(f"  срезов: {stats.slices}, строк меты: {stats.rows_meta}")
        print(f"  матчапов: {stats.rows_matchups}")
        if stats.period:
            print(f"  последний день данных: {stats.period}")
        if stats.errors:
            print(f"  ошибок: {len(stats.errors)}")
            for error in stats.errors[:10]:
                print(f"    - {error}")
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
