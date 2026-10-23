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

- **Свежая мета:** `winDay` с фильтром `gameModeIds=[ALL_PICK_RANKED]` — как в
  прошлом бета-релизе. Данные совпадают с референсными сайтами (dotabuff,
  opendota), в отличие от `stats` (без фильтра по режиму игры, данные
  размыты Turbo/Custom и другими режимами).
- `winDay` не支持 `bracketIds` (HTTP 400), поэтому загружается rank 0
  (все ранги) для каждой позиции 0..5. Бан-рейт по рангам берётся из
  `banDay` (уже загружено отдельно).
- winDay на 2026-10-21 отдаёт 17 дней с максимумом `2026-10-10` (разрыв
  2026-09-18…30). UI показывает фактический период из
  `vetmo_snapshots.snapshot_date`.
- **Позиции:** 6 срезов (позиции 0..5, rank 0), по 2159 строк каждый =
  127 героев × 17 дней.
- **Баны:** `banDay` за последние 7 дней; ban rate = баны / (10 × матчи)
  в рамках ранговой группы.
- **Контрпики:** `matchUp` за текущую неделю, без `bracketBasicIds: [ALL]` и
  без `matchLimit`.
- **Патчи:** `constants.gameVersions` — 189 версий, последняя `7.41f` (id 190).
  `winGameVersion` исторически неполный; не считать его источником патчей.
- **`window_days` в БД:** схема разрешает только `0` или `7`. Используется
  `7`, фактическая дата конца — `snapshot_date` (например `2026-10-10` —
  последний доступный день из winDay).

## Что уже сделано

1. `StratzClient.win_day(position, take)` — GraphQL-запрос `winDay` с
   `gameModeIds=[ALL_PICK_RANKED]`, без `bracketIds` (вызывает HTTP 400).
2. `aggregate_win_day()` — агрегация по дням с дельтами к предыдущему окну,
   pick rate, ban rate, флаг популярности.
3. `sync_all()` — баны из `banDay`, мета из `winDay` (6 позиций, rank 0),
   матчапы из `matchUp`, snapshot на последний доступный день.
4. Live-sync 2026-10-21: patch `7.41f`, 762 строк меты (127 героев × 6
   позиций), 6 срезов, период `2026-10-10`.

## Ограничения

- STRATZ не публикует полную документацию по `winDay`/`banDay`. `bracketIds`
  в `winDay` вызывает HTTP 400 — загружаем только все ранги (rank 0).
- `winDay` имеет разрыв в данных (2026-09-18…30 отсутствует) и лагает на
  11 дней от календаря. Период показывается честно из БД.
- Не печатать токен; не коммитить `.env`, `pop.txt`,
  `%APPDATA%/VETMO/secrets.env`.
