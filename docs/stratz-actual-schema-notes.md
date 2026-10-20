# STRATZ: фактические наблюдения по API (2026-10-20)

Это не опубликованная схема, а результаты live-introspection и пробных запросов.
Токен и значения секретов здесь отсутствуют.

## Endpoint / транспорт

- `POST https://api.stratz.com/graphql`
- `Authorization: Bearer <token>`, `User-Agent: VETMO/0.2`
- Python `httpx` получает Cloudflare `403 Just a moment...`.
- `curl.exe` проходит, `curl_cffi` с `impersonate="chrome"` тоже проходит.
  Для sync-скрипта использовать `curl_cffi.requests`, не голый `httpx`.

## Что реально есть в `HeroStatsQuery`

Поля (неполный список, важные):

- `winDay(heroIds, take, skip, bracketIds: [RankBracket], positionIds: [MatchPlayerPositionType], regionIds, gameModeIds, groupBy)`
  - `HeroWinDayType { day: Long, heroId, winCount, matchCount }`
  - `day` — epoch seconds.
  - В пробе `take: 3000`, `ALL_PICK` вернулось 2159 строк = 127 героев × 17 дней.
  - Диапазон в пробе: **2026-09-11 … 2026-10-10**, то есть данные могут отставать
    от календарной даты. В UI нельзя писать «сегодня»; показывать фактический период.
- `winWeek`, `winMonth`, `winGameVersion`, `winHour` — аналогичные агрегаты.
- `stats(heroIds, week, bracketBasicIds: [RankBracketBasicEnum], positionIds, groupByTime, groupByPosition, groupByBracket, minTime, maxTime)`
  - `HeroPositionTimeDetailType { heroId, week, time, position, bracketBasicIds, matchCount, remainingMatchCount, winCount, ... }`
  - `groupByPosition: true` даёт разбивку по позициям.
  - `groupByBracket: true` даёт 5 групп: `UNCALIBRATED`, `HERALD_GUARDIAN`,
    `CRUSADER_ARCHON`, `LEGEND_ANCIENT`, `DIVINE_IMMORTAL`.
  - `bracketBasicIds: [HERALD_GUARDIAN]` + `groupByPosition` даёт позиции внутри группы.
  - `bracketBasicIds: [ALL]` для `stats` вернул пустой список; не использовать `ALL` здесь.
  - `week` — номер недели (в пробе 2963); `time` — длительность/бакет, не дата.
- `matchUp(heroId, heroIds, week, bracketBasicIds: [RankBracketBasicEnum], orderBy, matchLimit, skip, take)`
  - `bracketBasicIds: [ALL]` даёт пустой ответ.
  - Без `bracketBasicIds` возвращает данные.
  - `matchLimit: 100` в пробе дал пустой ответ; без него — данные.
  - `HeroDryadType { heroId, with, matchCountWith, vs, matchCountVs }`
  - `vs: [HeroStatsHeroDryadType { heroId1, heroId2, week, matchCount, winCount, winsAverage, winRateHeroId1, winRateHeroId2, ... }]`
  - `count` в `vs` отсутствует; использовать `matchCount`.
  - `winsAverage` — доля 0..1; `winRateHeroId1` — общий WR героя, не матчапа.
- `heroVsHeroMatchup(heroId, week, bracketBasicIds, matchLimit, skip, take)` → `HeroMatchupType`
  - `advantage`/`disadvantage` в пробе с `[ALL]` были пустыми; проверять без `[ALL]`.
- `banDay(heroId: Short!, day: Int, bracketBasicIds: [RankBracketBasicEnum], take, skip, groupByDay, groupByRank)`
  - `HeroBanType { heroId, day, bracketBasicIds, matchCount, winCount }`
  - `day` — номер дня (например 20741), не epoch seconds.
  - В пробе `heroId: 44` вернул строки с **другими** heroId, то есть семантика
    аргумента неочевидна. Нужна отдельная проверка:
    1. запросить `banDay` для конкретного `day`;
    2. сравнить `Σ matchCount` с общим числом матчей за день;
    3. проверить, что для одного героя `matchCount` похож на ban count.
  - Если семантика не подтверждается — ban rate暫時 `null` (честное «—»), пока
    не найдём надёжный источник. Не подставлять pro-баны.
- `ratings` и `metaTrend` в фактическом API **отсутствуют**, хотя были в npm-схеме.
  Не использовать их.

## Практические выводы

- Для win/pick по точным рангам + позициям: `winDay`, последние 7 доступных дней.
- Для позиций и групп рангов: `stats` с `groupByPosition`/`groupByBracket`; это,
  похоже, более свежий недельный агрегат.
- Для дельт:
  - exact rank/position: сравнить два окна `winDay` (7 дней) или `stats` по неделям;
  - all-rank: `stats` текущая/предыдущая неделя;
  - если данных нет — `null`, не выдумывать.
- Для банов: сначала проверить `banDay`; при неубедительности — `null`.
- Для контрпиков: `matchUp` без `bracketBasicIds: [ALL]` и без `matchLimit`.
- `winGameVersion` в пробе вернул 18 426 строк, но только patch id до 181
  (7.40); текущие 182–190 отсутствовали. Не считать, что история патчей полная;
  проверять и, если нужно, строить историю из `stats`/`winWeek`.
- `constants.heroes` — 127 героев, `roles` — строки (`CARRY`, `ESCAPE`, `NUKER` ...),
  `stats.primaryAttribute` — `agi`/`str`/`int`/`all`, `stats.attackType` — `Melee`/`Ranged`.
- `constants.gameVersions` — 189 версий, последняя `7.41f` (id 190).

## Что должен сделать api-agent

1. Добить семантику `banDay` на 2–3 героях и сохранить вывод в этом файле.
2. Определить, какой источник даёт актуальные 7 дней: `winDay` (лаг) vs `stats`
   (неделя). Зафиксировать в `docs/stratz-validation.md`.
3. Снять фикстуры реальных ответов в `tests/fixtures/stratz/`.
4. Не печатать токен; не коммитить `.env`, `pop.txt`, `%APPDATA%/VETMO/secrets.env`.
