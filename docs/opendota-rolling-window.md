# OpenDota: скользящее окно 7 дней

## Что берём из OpenDota

`GET /api/heroStats` возвращает:

| Поле | Смысл |
|---|---|
| `pub_pick`, `pub_win` | сумма public-пиков/побед за последние 7 дней |
| `pub_pick_trend[7]`, `pub_win_trend[7]` | те же значения, разбитые по дням |
| `1_pick..7_pick`, `1_win..7_win` | суммы за 7 дней по рангам |
| `pro_pick`, `pro_win`, `pro_ban` | pro-сцена |
| `turbo_picks`, `turbo_wins` | turbo |

Проверка: `sum(pub_pick_trend) == pub_pick`, `sum(pub_win_trend) == pub_win`.
Последний элемент тренда — текущие неполные сутки.

## Как храним

Миграция `supabase/migrations/20261023_005_hero_daily.sql` добавляет
`vetmo_hero_daily` — дневные инкременты:

```text
stat_date, patch_id, hero_id, rank_tier, position, game_mode,
match_count, win_count, source
```

`sync_opendota_meta()` при каждом запуске:

1. разбирает `pub_pick_trend` / `pub_win_trend`;
2. пишет последние 7 дней в `vetmo_hero_daily` (upsert);
3. считает `rank_tier=0` как сумму за `current_date - 6 .. current_date`;
4. пишет результат в `vetmo_meta` с `window_days=7`.

Если таблицы ещё нет, sync не падает: дневные строки считаются в памяти,
а ошибка попадает в `vetmo_sync_runs.details`.

## Дельты

`delta_win` / `delta_pick` считаются относительно предыдущего доступного
снимка (`vetmo_snapshots`), обычно вчерашнего. Это даёт дневное изменение.
Если синк пропущен, берётся ближайший более ранний снимок.

## Ограничения

- `pub_*_trend` — календарные дни, а не точные 168 часов.
- Дневных трендов по рангам 1..7 в `heroStats` нет: для них окно
  по-прежнему берётся из суммарных `{rank}_pick/{rank}_win`.
- `heroStats` — public-матчи, не гарантированно только ranked all pick.
- Позиций 1..5 в `heroStats` нет; они приходят из STRATZ.
