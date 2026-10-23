# Проверка достоверности меты VETMO (2026-10-20)

## Что проверяли

- Винрейты и пикрейты 127 героев в `vetmo_meta` (rank 0 = все ранги, position 0).
- Сверка с независимым источником — Dotabuff, недельный срез (`?date=week`).
- Семантику `winDay` / `banDay` в STRATZ GraphQL (live-интроспекция).
- Корректность нормализации банов.

## Главный вывод

Арифметика агрегации была верна (сумма винрейтов по 127 героям = ровно
**50.000 %** на каждом ранге), но использовался не тот режим игры:
STRATZ `ALL_PICK` — это фактически **unranked** All Pick (≈789 тыс.
матчей/неделя), а Dotabuff считает **ranked** All Pick (≈3.6 млн
матчей/неделя). Переключение на `ALL_PICK_RANKED` убрало систематическое
расхождение.

## Результат сверки с Dotabuff (126 из 127 героев)

| Метрика | Значение |
|---|---|
| Среднее абсолютное расхождение WR | **0.267 п.п.** |
| Медиана | **0.215 п.п.** |
| 95-й перцентиль | **0.721 п.п.** |
| Максимум | **1.146 п.п.** (Meepo, пикрейт 1.6 %) |

Ключевые герои:

| Герой | Dotabuff WR | VETMO WR | Δ |
|---|---:|---:|---:|
| Wraith King | 54.90 | 55.08 | +0.18 |
| Outworld Destroyer | 53.42 | 53.70 | +0.28 |
| Phantom Lancer | 53.22 | 53.25 | +0.03 |
| Crystal Maiden | 51.76 | 51.69 | −0.07 |
| Necrophos | 50.70 | 50.87 | +0.17 |
| Bristleback | 49.04 | 48.59 | −0.45 |
| Pudge | 51.18 | 51.10 | −0.08 |
| Juggernaut | 52.59 | 52.88 | +0.29 |
| Phantom Assassin | 51.30 | 51.21 | −0.09 |
| Lifestealer | 51.47 | 51.69 | +0.22 |

Пикрейты также совпадают в пределах ~1–2 п.п. (WK 12.07 vs 12.88,
Pudge 27.61 vs 28.25, PA 12.66 vs 12.75).

**Вывод: WK с винрейтом ~55 % — не баг.** Это реальный результат недели:
Dotabuff показывает 54.90 %. Предыдущие 55.64 % были из unranked-пула.

## Что было исправлено в коде

- `WIN_DAY_QUERY`: `gameModeIds: [ALL_PICK]` → `[ALL_PICK_RANKED]`.
- `game_mode` в `vetmo_meta`/`vetmo_snapshots` → `ALL_PICK_RANKED`.
- RPC `vetmo_get_meta_report` фильтрует `ALL_PICK_RANKED`.
- Подпись в UI: `Ranked All Pick`.
- Старые строки `ALL_PICK` удалены из Supabase.

## Баны (`banDay`) — рабочая семантика

Live-интроспекция и серия запросов показали:

- `heroId` обязателен, но **игнорируется** — API всегда отдаёт все 127 героев.
- `take` — это **число дней истории**, а не строк (`take=30` → 30 дней).
- `day` — **индекс дня** (не unix-время), `day=null` только без группировки
  (тогда отдаются lifetime-суммы).
- `groupByDay`/`groupByRank` дают строки `hero × day × bracket`.
- `bracketBasicIds` — 5 групп: `UNCALIBRATED`, `HERALD_GUARDIAN`,
  `CRUSADER_ARCHON`, `LEGEND_ANCIENT`, `DIVINE_IMMORTAL`.
- Выборка `banDay` меньше полного пула матчей, поэтому абсолютный ban rate
  нормируется на сумму банов всех героев:
  `ban_rate = bans_hero / (Σbans / 10) × 100`
  (10 банов на матч в Ranked All Pick).

Полученные ban rate (ранг 0, окно 04.10–10.10.2026):

| Герой | Ban rate |
|---|---:|
| Outworld Destroyer | 46.1 % |
| Phantom Lancer | 41.4 % |
| Lifestealer | 38.3 % |
| Lina | 33.6 % |
| Necrophos | 23.0 % |
| Night Stalker | 21.7 % |
| Invoker | 18.6 % |
| Slark | 18.3 % |
| Wraith King | 2.4 % |

Значения доменно правдоподобны: банят сильных/неудобных героев, а не
просто героев с высоким винрейтом (WK — 55 % WR, но всего 2.4 % банов).

## Ограничения

- `winDay` STRATZ отстаёт примерно на 10 дней: последняя дата — 2026-10-10.
  **На 2026-10-21 это исправлено переходом на `stats` текущей недели**;
  см. `docs/stratz-actual-schema-notes.md`. Период честно показывается в
  подзаголовке карточки.
- `banDay` — сэмплированная выборка; абсолютные ban rate зависят от
  допущения «10 банов на матч». Относительный порядок устойчив.
- Группы `bracketBasicIds` объединяют ранги: Divine и Immortal попадают в
  один срез, поэтому ban rate для rank 7 и 8 одинаков.

## Артефакты

- `docs/qa-dotabuff-vs-vetmo.json` — построчная сверка 126 героев.
- `tests/unit/test_stratz_aggregate.py` — тесты нормализации банов и режима.
- `src/vetmo/services/stratz_aggregate.py` — `ban_rates_by_rank`,
  `_day_index`, `BANS_PER_MATCH`.
