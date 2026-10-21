# STRATZ: фактические наблюдения по API (2026-10-21)

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
  - **На 2026-10-21 `winDay` отдаёт только 17 дней: 2026-09-11…17 и
    2026-10-01…10.** Пропуск 2026-09-18…30 и отставание от календаря на
    11 дней. `take=10000` и `skip` этот разрыв не исправляют.
  - `winDay` больше не используется как источник свежей меты.
- `winWeek`, `winMonth`, `winGameVersion`, `winHour` — аналогичные агрегаты.
  - `winWeek` заканчивается неделей `2026-10-01`.
  - `winMonth` — августом 2026.
  - `winHour` — только последние ~30 часов.
  - Для недельной меты не подходят.
- `stats(heroIds, week, bracketBasicIds: [RankBracketBasicEnum], positionIds, groupByTime, groupByPosition, groupByBracket, minTime, maxTime)`
  - `HeroPositionTimeDetailType { heroId, week, time, position, bracketBasicIds, matchCount, remainingMatchCount, winCount, ... }`
  - **`week` — unix-время начала недели, а не номер недели.** Недели STRATZ
    начинаются в четверг. `week=1792022400` — неделя `2026-10-15…21`.
  - `groupByPosition: true` + `groupByBracket: true` даёт 3175 строк =
    127 героев × 5 позиций × 5 групп.
  - Группы: `UNCALIBRATED`, `HERALD_GUARDIAN`, `CRUSADER_ARCHON`,
    `LEGEND_ANCIENT`, `DIVINE_IMMORTAL`.
  - `bracketBasicIds: [ALL]` для `stats` возвращает пустой список; не использовать `ALL`.
  - Позиции приходят как `POSITION_1`…`POSITION_5`.
  - Суммы сходятся: по каждой позиции pick rate героев ≈ 100%, по всем
    позициям (position=0) ≈ 1000% — в матче 10 слотов героев.
- `matchUp(heroId, heroIds, week, bracketBasicIds: [RankBracketBasicEnum], orderBy, matchLimit, skip, take)`
  - `bracketBasicIds: [ALL]` даёт пустой ответ.
  - Без `bracketBasicIds` возвращает данные.
  - `matchLimit: 100` в пробе дал пустой ответ; без него — данные.
  - `HeroDryadType { heroId, with, matchCountWith, vs, matchCountVs }`
  - `vs: [HeroStatsHeroDryadType { heroId1, heroId2, week, matchCount, winCount, winsAverage, winRateHeroId1, winRateHeroId2, ... }]`
  - `count` в `vs` отсутствует; использовать `matchCount`.
  - `winsAverage` — доля 0..1; `winRateHeroId1` — общий WR героя, не матчапа.
  - На 2026-10-21 `matchUp` содержит текущую неделю с `2026-10-15`.
- `heroVsHeroMatchup(heroId, week, bracketBasicIds, matchLimit, skip, take)` → `HeroMatchupType`
  - `advantage`/`disadvantage` в пробе с `[ALL]` были пустыми; проверять без `[ALL]`.
- `banDay(heroId: Short!, day: Int, bracketBasicIds: [RankBracketBasicEnum], take, skip, groupByDay, groupByRank)`
  - `HeroBanType { heroId, day, bracketBasicIds, matchCount, winCount }`
  - `day` — номер дня (например 20741), не epoch seconds.
  - На 2026-10-21 `banDay` свежий: есть данные по `2026-10-21`.
  - В пробе `heroId: 44` вернул строки с **другими** heroId, то есть семантика
    аргумента неочевидна; sync читает общий срез `banDay` без фильтра по герою
    и агрегирует по `heroId`.
- `ratings` и `metaTrend` в фактическом API **отсутствуют**, хотя были в npm-схеме.
  Не использовать их.

## Практические выводы

- **Свежая мета:** `stats` текущей недели (`week` = unix-время четверга).
  Для дельт — та же `stats` за предыдущую неделю.
- **Позиции и ранги:** один запрос `stats` с `groupByPosition` +
  `groupByBracket`; ранг 0 суммирует все 5 групп, ранги 1/2 → `HERALD_GUARDIAN`,
  3/4 → `CRUSADER_ARCHON`, 5/6 → `LEGEND_ANCIENT`, 7/8 → `DIVINE_IMMORTAL`.
- **Баны:** `banDay` за последние 7 дней; ban rate = баны / (10 × матчи)
  в рамках ранговой группы.
- **Контрпики:** `matchUp` за текущую неделю, без `bracketBasicIds: [ALL]` и
  без `matchLimit`.
- **Патчи:** `constants.gameVersions` — 189 версий, последняя `7.41f` (id 190).
  `winGameVersion` исторически неполный; не считать его источником патчей.
- **`window_days` в БД:** схема разрешает только `0` или `7`. Для свежей
  недели используется `7`, а фактическая дата конца — `snapshot_date`
  (например `2026-10-21`).

## Что уже сделано

1. `StratzClient.hero_stats_week(week)` — GraphQL-запрос `stats` с
   `groupByPosition`/`groupByBracket`.
2. `aggregate_hero_stats_week()` — 54 среза rank 0..8 × position 0..5,
   pick share, дельты, баны, флаг популярности.
3. `sync_all()` — свежие баны, `stats` текущей/предыдущей недели, матчапы
   текущей недели, snapshot на дату конца недели.
4. Live-sync 2026-10-21: patch `7.41f`, 6858 строк меты, 54 среза,
   32512 строк матчапов, период `15.10 – 21.10.2026`.

## Ограничения

- STRATZ не публикует полную документацию по составу `stats`/`banDay`
  (кастомы, ремейки, точный фильтр «нормальных игр»). Семантика проверена
  косвенно: суммы позиций и рангов сходятся с числом матчей.
- Не печатать токен; не коммитить `.env`, `pop.txt`,
  `%APPDATA%/VETMO/secrets.env`.
