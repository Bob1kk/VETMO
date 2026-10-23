"""Временная проверка оценок Herald+Mid через OpenDota + STRATZ (не коммитить)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from vetmo.infra.sync_settings import SyncSettings
from vetmo.services.stratz_client import StratzClient

HEROES = {
    145: ("Kez", 56.67, 9.36), 14: ("Pudge", 56.49, 16.35), 49: ("Dragon Knight", 56.10, 7.68),
    26: ("Lion", 55.56, 9.55), 136: ("Marci", 54.75, 19.72), 6: ("Windranger", 54.59, 25.84),
    105: ("Techies", 53.71, 10.92), 63: ("Weaver", 53.64, 6.87), 86: ("Rubick", 53.63, 11.17),
    101: ("Skywrath Mage", 53.30, 12.30), 22: ("Drow Ranger", 53.15, 13.86),
    61: ("Broodmother", 52.75, 19.29), 56: ("Clinkz", 52.72, 14.92),
    120: ("Nature's Prophet", 52.70, 9.24), 7: ("Earthshaker", 51.85, 20.22),
    93: ("Monkey King", 51.72, 10.86), 35: ("Sniper", 51.32, 58.98),
    36: ("Necrophos", 51.19, 42.07), 47: ("Viper", 50.96, 32.58),
    46: ("Templar Assassin", 50.26, 11.92), 15: ("Razor", 50.00, 10.86),
    126: ("Void Spirit", 50.00, 12.36), 17: ("Storm Spirit", 49.20, 27.27),
    76: ("Outworld Destroyer", 48.83, 39.88), 19: ("Invoker", 48.81, 52.30),
    90: ("Keeper of the Light", 48.80, 18.16), 82: ("Meepo", 48.72, 12.17),
    113: ("Arc Warden", 48.71, 26.65),
}

STATS_QUERY = """
query($week: Long) {
  heroStats {
    stats(week: $week, groupByPosition: true) {
      heroId position matchCount winCount
    }
  }
}
"""


def week_start(dt: datetime) -> int:
    days_back = (dt.weekday() - 3) % 7
    start = (dt - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def pick_rate(picks: int, total_picks: int) -> float:
    return 1000.0 * picks / total_picks if total_picks else 0.0


def main() -> int:
    sync = SyncSettings.load()
    client = StratzClient(sync.stratz_token, url=sync.stratz_api_url)
    now = datetime.now(UTC)
    week = week_start(now)
    try:
        data = client.execute(STATS_QUERY, {"week": week})
        rows = ((data.get("heroStats") or {}).get("stats")) or []
    finally:
        client.close()

    positions = sorted({str(r.get("position")) for r in rows})
    print("STRATZ positions:", positions, "rows:", len(rows))

    # total all-rank picks and mid picks
    total_all = 0
    total_mid = 0
    per_hero: dict[int, dict[str, list[int]]] = {}
    for row in rows:
        hid = int(row["heroId"])
        pos = str(row.get("position"))
        bucket = per_hero.setdefault(hid, {})
        agg = bucket.setdefault(pos, [0, 0])
        agg[0] += int(row.get("matchCount") or 0)
        agg[1] += int(row.get("winCount") or 0)
        if pos[0] == "P" or pos.startswith("POSITION"):
            total_all += int(row.get("matchCount") or 0)
        if pos in ("POSITION_2", "2"):
            total_mid += int(row.get("matchCount") or 0)
    print("STRATZ total position-slots:", total_all, "mid slots:", total_mid)

    od = httpx.get("https://api.opendota.com/api/heroStats", timeout=60).json()
    od_by_id = {int(h["id"]): h for h in od}
    tier_picks = {i: int(od_by_id[i].get("1_pick") or 0) for i in HEROES if i in od_by_id}
    total_tier_picks = sum(int(h.get("1_pick") or 0) for h in od)
    print("OpenDota total tier1 picks:", total_tier_picks)

    print(f"\n{'hero':18s} {'DB WR':>6s} {'est WR':>7s} {'od WR':>6s} {'off':>6s} | {'DB pick':>7s} {'est':>6s} {'od':>6s} {'share':>6s}")
    for hid, (name, db_wr, db_pick) in HEROES.items():
        if hid not in od_by_id or hid not in per_hero:
            print(f"{name:18s} MISSING")
            continue
        hero = od_by_id[hid]
        t1_pick = int(hero.get("1_pick") or 0)
        t1_win = int(hero.get("1_win") or 0)
        od_wr = 100.0 * t1_win / t1_pick if t1_pick else 0.0
        od_pick = pick_rate(t1_pick, total_tier_picks)

        stats = per_hero[hid]
        all_m = sum(v[0] for k, v in stats.items() if k.startswith("POSITION"))
        all_w = sum(v[1] for k, v in stats.items() if k.startswith("POSITION"))
        mid_m = stats.get("POSITION_2", [0, 0])[0]
        mid_w = stats.get("POSITION_2", [0, 0])[1]
        s_wr_all = 100.0 * all_w / all_m if all_m else 0.0
        s_wr_mid = 100.0 * mid_w / mid_m if mid_m else 0.0
        offset = s_wr_mid - s_wr_all
        est_wr = od_wr + offset
        share = mid_m / all_m if all_m else 0.0
        est_pick = od_pick * share

        print(
            f"{name:18s} {db_wr:6.2f} {est_wr:7.2f} {od_wr:6.2f} {offset:+6.2f} | "
            f"{db_pick:7.2f} {est_pick:6.2f} {od_pick:6.2f} {share:6.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
