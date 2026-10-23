"""Временный скрипт диагностики Supabase (не коммитить)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from vetmo.infra.sync_settings import SyncSettings


def get(client: httpx.Client, path: str, **params):
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def main() -> int:
    sync = SyncSettings.load()
    headers = {
        "apikey": sync.service_key,
        "Authorization": f"Bearer {sync.service_key}",
    }
    base = sync.supabase_url.rstrip("/") + "/rest/v1/"
    with httpx.Client(base_url=base, headers=headers, timeout=60) as client:
        patches = get(client, "vetmo_patches", select="*", order="id.desc", limit=20)
        print("PATCHES:")
        for row in patches:
            print(" ", row)

        rows = get(
            client,
            "vetmo_meta",
            select="source,patch_id,rank_tier,position,window_days,game_mode",
            limit=100000,
        )
        counter = Counter(
            (
                row.get("source"),
                row.get("patch_id"),
                row.get("rank_tier"),
                row.get("position"),
                row.get("window_days"),
                row.get("game_mode"),
            )
            for row in rows
        )
        print(f"\nMETA ROWS: {len(rows)}; groups={len(counter)}")
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))[:60]:
            print(" ", key, count)

        for label, filters in (
            ("rank1/pos2", {"rank_tier": "eq.1", "position": "eq.2"}),
            ("rank1/pos0", {"rank_tier": "eq.1", "position": "eq.0"}),
            ("rank0/pos0", {"rank_tier": "eq.0", "position": "eq.0"}),
        ):
            print(f"\nSAMPLE {label}:")
            sample = get(
                client,
                "vetmo_meta",
                select=(
                    "hero_id,rank_tier,position,source,patch_id,window_days,game_mode,"
                    "win_rate,pick_rate,ban_rate,match_count,delta_win,delta_pick"
                ),
                order="win_rate.desc",
                limit=8,
                **filters,
            )
            for row in sample:
                print(" ", row)

        snaps = get(
            client,
            "vetmo_snapshots",
            select="snapshot_date,source,rank_tier,position,window_days",
            limit=100000,
        )
        snap_counter = Counter(
            (row.get("snapshot_date"), row.get("source"), row.get("rank_tier"), row.get("position"))
            for row in snaps
        )
        print(f"\nSNAPSHOTS: {len(snaps)}; groups={len(snap_counter)}")
        for key, count in sorted(snap_counter.items(), key=lambda item: str(item[0]))[:40]:
            print(" ", key, count)

        runs = get(
            client, "vetmo_sync_runs", select="*", order="id.desc", limit=6
        )
        print("\nSYNC RUNS:")
        for row in runs:
            print(" ", {k: row.get(k) for k in (
                "id", "started_at", "finished_at", "status", "source",
                "patch_version", "rows_meta", "rows_matchups", "error")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
