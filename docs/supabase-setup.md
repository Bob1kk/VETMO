# Supabase setup для VETMO 0.2

Проект: `https://qtqntybxwwhggqimkxpi.supabase.co`  
Все таблицы VETMO имеют префикс `vetmo_`, чтобы не пересекаться с уже существующими
`allowed_teachers`, `profiles`, `substitution`, `substitutions`, `users`.

## 1. Применить схему

Нужен доступ к Supabase SQL Editor (или DB password / Management API).
`service_role` через PostgREST **не умеет выполнять DDL**, поэтому одного ключа
недостаточно.

1. Открой Supabase Dashboard → **SQL Editor** → **New query**.
2. Вставь содержимое `supabase/migrations/20261020_001_init.sql`.
3. Нажми **Run**. Ожидаемо: `Success. No rows returned`.
4. Новый запрос: вставь `supabase/seed/20261020_002_seed_heroes.sql`.
5. Run. Проверь:

```sql
select count(*) from public.vetmo_heroes;          -- 127
select count(*) from public.vetmo_patches;         -- 0, заполнит sync
select * from public.v_vetmo_sync_status;          -- пусто, пока не было sync
```

## 2. Включить anonymous auth

Dashboard → **Authentication** → **Providers** → **Anonymous** → Enable.

Без этого reference-данные (герои/мета) всё равно читаются, но настройки и
драфты не смогут писать в `vetmo_profiles`/`vetmo_drafts`.

## 3. Ключи

### Приложение

В `.env` проекта:

```dotenv
VETMO_SUPABASE_URL=https://qtqntybxwwhggqimkxpi.supabase.co
VETMO_SUPABASE_ANON_KEY=sb_publishable_...
```

`anon`/`publishable` — публичный ключ, может попасть в exe. RLS не даёт ему
писать reference-таблицы.

### Sync-скрипт

В `%APPDATA%\VETMO\secrets.env` (вне OneDrive, не в git):

```dotenv
VETMO_SYNC_SUPABASE_URL=https://qtqntybxwwhggqimkxpi.supabase.co
VETMO_SYNC_SERVICE_KEY=...
VETMO_SYNC_STRATZ_TOKEN=...
```

`service_role` обходит RLS. Никогда не вставляй его в exe, `.env` проекта,
GitHub или чат. При утечке — rotate в Dashboard → Project Settings → API.

## 4. Проверка

```powershell
.\.venv\Scripts\python.exe scripts\check_supabase_schema.py
```

Скрипт печатает только имена таблиц/статусы, без значений ключей.

Проверка RLS вручную:

```sql
-- anon должен читать
select count(*) from public.vetmo_heroes;

-- anon не должен писать (ожидаем ошибку/permission denied)
insert into public.vetmo_heroes(id, name, localized_name)
values (99999, 'npc_dota_hero_test', 'Test');
```

## 5. Sync

```powershell
.\.venv\Scripts\python.exe -m vetmo.tools.sync_stratz --full --dry-run
.\.venv\Scripts\python.exe -m vetmo.tools.sync_stratz --full
```

Первый запуск заполняет `vetmo_patches`, `vetmo_meta`, `vetmo_snapshots`,
`vetmo_hero_matchups`, `vetmo_news`, `vetmo_sync_runs`.

## 6. Что смотреть в Dashboard

- `public.v_vetmo_meta` — человекочитаемая мета (герой, патч, ранг, позиция, WR/pick/ban).
- `public.v_vetmo_sync_status` — последний sync.
- `public.vetmo_heroes` — 127 героев.
- `public.vetmo_meta` — сырые строки; `position=0` — all positions, `rank_tier=0` — all ranks.
- `public.vetmo_snapshots` — история для дельт.

## 7. Важно про данные STRATZ

- Источник свежей меты — `stats` за текущую неделю (`week` — unix-время
  начала недели, четверг). `winDay` в октябре 2026 отставал на 11 дней и
  содержал разрыв; `winWeek`/`winMonth` ещё старше.
- UI показывает фактический период из `vetmo_snapshots.snapshot_date`, а не
  «сегодня» (например `15.10 – 21.10.2026`).
- `metaTrend` и `ratings` в фактическом API отсутствуют.
- Баны — из `banDay` за 7 дней; ban rate считается на 10 банов на матч.
- Подробности — в `docs/stratz-actual-schema-notes.md`.
