import json
from curl_cffi import requests

token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJTdWJqZWN0IjoiZDdkMDhjNzMtN2U0My00MDA4LTg3MGMtZWI0YzFlODA5NjVmIiwiU3RlYW1JZCI6IjE1MTgyNDUzNTgiLCJBUElVc2VyIjoidHJ1YSIiLCJuYmYiOjE3OTI1MDYxOTgsImV4cCI6MTgyNDA0MjE5OCwiaWF0IjoxNzk2NDA2MTk4LCJpc3MiOiJodHRwczovL2FwaS5zdHJhdHouY29tIn0.EvPQ-WVxJTMHY5FQCqd7r50cVzvlFJijuuMjhZKP6t4'

query = """
query($take: Int!) {
  heroStats {
    winDay(
      take: $take
      gameModeIds: [ALL_PICK_RANKED]
    ) {
      day
      heroId
      winCount
      matchCount
    }
  }
}
"""

session = requests.Session(impersonate="chrome")
session.headers.update({
    "Authorization": f"Bearer {token}",
    "User-Agent": "VETMO/0.2",
    "Content-Type": "application/json",
})

resp = session.post("https://api.stratz.com/graphql", json={"query": query, "variables": {"take": 3000}}, timeout=90)
print("Status:", resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    if data.get("errors"):
        print("ERRORS:", data["errors"])
    else:
        rows = data.get("data", {}).get("heroStats", {}).get("winDay", [])
        print("Rows count:", len(rows))
        days = sorted(set(r.get("day") for r in rows if r.get("day") is not None))
        print("Days:", days[:5], "...", days[-5:] if days else [])
        print("Unique heroes:", len(set(r.get("heroId") for r in rows)))
        with open("stratz_winday_raw.json", "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print("Saved to stratz_winday_raw.json")
else:
    print("Body:", resp.text[:1000])
