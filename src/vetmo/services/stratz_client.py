"""Минимальный STRATZ GraphQL-клиент для sync-скрипта.

Обычный httpx/requests получает Cloudflare 403; curl_cffi с impersonate
Chrome проходит. Токен передаётся только в заголовке и нигде не логируется.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from curl_cffi import requests

logger = logging.getLogger("vetmo.stratz")

WIN_DAY_QUERY = """
query($take: Int!, $bracketIds: [RankBracket!], $positionIds: [MatchPlayerPositionType!]) {
  heroStats {
    winDay(
      take: $take
      bracketIds: $bracketIds
      positionIds: $positionIds
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

CONSTANTS_QUERY = """
query {
  constants {
    gameVersions { id name }
  }
}
"""

MATCHUP_QUERY = """
query(
  $heroIds: [Short!]
  $take: Int
  $week: Long
  $bracketIds: [RankBracketBasicEnum]
) {
  heroStats {
    matchUp(
      heroIds: $heroIds
      take: $take
      week: $week
      bracketBasicIds: $bracketIds
    ) {
      heroId
      vs {
        heroId2
        matchCount
        winCount
        winsAverage
      }
      with {
        heroId2
        matchCount
        winCount
        winsAverage
      }
    }
  }
}
"""

BAN_DAY_QUERY = """
query($heroId: Short!, $take: Int, $groupByDay: Boolean, $groupByRank: Boolean) {
  heroStats {
    banDay(
      heroId: $heroId
      take: $take
      groupByDay: $groupByDay
      groupByRank: $groupByRank
    ) {
      heroId
      day
      bracketBasicIds
      matchCount
      winCount
    }
  }
}
"""


class StratzError(RuntimeError):
    """STRATZ вернул GraphQL/HTTP-ошибку."""


class StratzClient:
    """Тонкий клиент с ретраями и без утечки токена в логи."""

    def __init__(self, token: str, url: str = "https://api.stratz.com/graphql") -> None:
        self._url = url
        self._session: requests.Session = requests.Session(impersonate="chrome")
        proxy = os.environ.get("VETMO_SYNC_STRATZ_PROXY", "").strip()
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "VETMO/0.2",
            "Content-Type": "application/json",
        })

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Выполняет запрос; 3 попытки на 429/5xx/сетевые ошибки."""
        payload = {"query": query, "variables": variables or {}}
        last: Exception | None = None
        for attempt in range(3):
            try:
                response = self._session.post(self._url, json=payload, timeout=90)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("errors"):
                        message = str(data["errors"][0].get("message", "STRATZ error"))
                        raise StratzError(message)
                    return data.get("data") or {}
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.0 + attempt)
                    continue
                raise StratzError(f"HTTP {response.status_code}")
            except StratzError:
                raise
            except Exception as exc:  # noqa: BLE001 - транспорт/JSON
                last = exc
                if attempt < 2:
                    time.sleep(1.0 + attempt)
                    continue
        raise StratzError(f"STRATZ недоступен: {type(last).__name__}")

    def win_day(
        self,
        *,
        bracket: str | None,
        position: int | None,
        take: int = 3000,
    ) -> list[dict[str, Any]]:
        """Сырые строки winDay (127 героев × доступные дни)."""
        variables: dict[str, Any] = {"take": int(take)}
        if bracket:
            variables["bracketIds"] = [bracket]
        if position is not None and int(position) > 0:
            variables["positionIds"] = [f"POSITION_{int(position)}"]
        data = self.execute(WIN_DAY_QUERY, variables)
        rows = ((data.get("heroStats") or {}).get("winDay")) or []
        return [row for row in rows if isinstance(row, dict)]

    def game_versions(self) -> list[dict[str, Any]]:
        """Список патчей STRATZ (id + name)."""
        data = self.execute(CONSTANTS_QUERY)
        rows = ((data.get("constants") or {}).get("gameVersions")) or []
        return [row for row in rows if isinstance(row, dict)]

    def matchup_groups(
        self,
        hero_ids: list[int],
        *,
        take: int = 300,
        week: int | None = None,
        bracket: str | None = None,
    ) -> dict[int, dict[str, list[dict[str, Any]]]]:
        """Матчапы сразу для пачки героев.

        Возвращает ``hero_id -> {"vs": [...], "with": [...]}``. Один запрос
        с ``heroIds`` экономит 127 отдельных вызовов; ``week`` — unix-время
        начала последней полной недели, ``bracket`` — группа рангов STRATZ.
        """
        ids = [int(hero_id) for hero_id in hero_ids if int(hero_id) > 0]
        if not ids:
            return {}
        variables: dict[str, Any] = {
            "heroIds": ids,
            "take": max(1, int(take)),
        }
        if week is not None:
            variables["week"] = int(week)
        if bracket:
            variables["bracketIds"] = [str(bracket)]
        data = self.execute(MATCHUP_QUERY, variables)
        groups = ((data.get("heroStats") or {}).get("matchUp")) or []
        result: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for group in groups:
            if not isinstance(group, dict):
                continue
            try:
                hero_id = int(group.get("heroId") or 0)
            except (TypeError, ValueError):
                continue
            if hero_id <= 0:
                continue
            result[hero_id] = {
                "vs": [
                    row for row in (group.get("vs") or [])
                    if isinstance(row, dict)
                ],
                "with": [
                    row for row in (group.get("with") or [])
                    if isinstance(row, dict)
                ],
            }
        return result

    def matchups(self, hero_id: int, take: int = 100) -> list[dict[str, Any]]:
        """Совместимость: только vs-строки одного героя."""
        groups = self.matchup_groups([int(hero_id)], take=take)
        return list((groups.get(int(hero_id)) or {}).get("vs") or [])

    def ban_day(
        self,
        *,
        hero_id: int | None = None,
        days: int = 30,
        group_by_day: bool = True,
        group_by_rank: bool = True,
    ) -> list[dict[str, Any]]:
        """Бан-статистика STRATZ по героям/дням/ранговым группам.

        Особенности API (проверено live):
        - аргумент ``heroId`` обязателен, но ИГНОРИРУЕТСЯ: всегда возвращаются
          строки по всем героям (127 уникальных ``heroId``);
        - ``take`` — число ДНЕЙ истории, а не строк (``take=30`` -> 30 дней);
        - ``day`` — индекс дня (не unix-время), ``day=null`` только без
          группировки (тогда отдаются lifetime-суммы);
        - ``bracketBasicIds`` — 5 групп рангов: UNCALIBRATED,
          HERALD_GUARDIAN, CRUSADER_ARCHON, LEGEND_ANCIENT, DIVINE_IMMORTAL;
        - ``matchCount`` — число матчей, где герой забанен (выборка STRATZ
          меньше полного пула, поэтому абсолютный ban rate нормируется на
          сумму банов всех героев: при 10 банах на матч
          ``ban_rate = bans_hero / (sum_bans / 10) * 100``).
        """
        variables: dict[str, Any] = {
            "heroId": int(hero_id) if hero_id is not None else 1,
            "take": int(days),
            "groupByDay": group_by_day,
            "groupByRank": group_by_rank,
        }
        data = self.execute(BAN_DAY_QUERY, variables)
        rows = ((data.get("heroStats") or {}).get("banDay")) or []
        return [row for row in rows if isinstance(row, dict)]

    def close(self) -> None:
        self._session.close()


__all__ = ["StratzClient", "StratzError"]
