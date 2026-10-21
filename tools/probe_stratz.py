"""Probe STRATZ GraphQL через curl_cffi (как в StratzClient)."""

from __future__ import annotations

import os
import sys

from curl_cffi import requests


def main() -> int:
    token = os.environ.get("VETMO_SYNC_STRATZ_TOKEN")
    if not token:
        print("VETMO_SYNC_STRATZ_TOKEN не задан", file=sys.stderr)
        return 2

    proxy = os.environ.get("VETMO_SYNC_STRATZ_PROXY", "").strip()
    kwargs: dict[str, object] = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        "json": {"query": "query { __typename }"},
        "impersonate": "chrome",
        "timeout": 30,
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}

    response = requests.post(
        "https://api.stratz.com/graphql",
        **kwargs,
    )
    print(f"STRATZ HTTP status: {response.status_code}")
    if response.status_code != 200:
        print(response.text[:500], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
