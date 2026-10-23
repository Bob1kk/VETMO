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

# Try different header configurations
configs = [
    {
        "name": "Bearer in Authorization",
        "headers": {
            "Authorization": f"Bearer {token}",
            "User-Agent": "VETMO/0.2",
            "Content-Type": "application/json",
        }
    },
    {
        "name": "Token directly in Authorization",
        "headers": {
            "Authorization": token,
            "User-Agent": "VETMO/0.2",
            "Content-Type": "application/json",
        }
    },
    {
        "name": "X-Stratz-Token header",
        "headers": {
            "X-Stratz-Token": token,
            "User-Agent": "VETMO/0.2",
            "Content-Type": "application/json",
        }
    },
]

for cfg in configs:
    print(f"\n=== {cfg['name']} ===")
    session = requests.Session(impersonate="chrome")
    session.headers.update(cfg["headers"])
    try:
        resp = session.post("https://api.stratz.com/graphql", json={"query": query, "variables": {"take": 3000}}, timeout=90)
        print("Status:", resp.status_code)
        print("Body:", resp.text[:300])
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("data", {}).get("heroStats", {}).get("winDay", [])
            print("Rows:", len(rows))
            with open("stratz_winday_raw.json", "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            print("SAVED!")
            break
    except Exception as e:
        print("Exception:", type(e).__name__, str(e)[:200])
