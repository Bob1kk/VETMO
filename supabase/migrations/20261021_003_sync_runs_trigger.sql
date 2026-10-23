-- VETMO — трассировка запусков sync: источник и request_id.
-- Применять после 20261020_002_matchups.sql. Миграция идемпотентна.
--
-- Колонка называется trigger_source, а не trigger: ``trigger`` —
-- зарезервированное слово PostgreSQL, использовать его как имя колонки
-- без кавычек нельзя (PostgREST такую колонку тоже не увидит).

alter table public.vetmo_sync_runs
    add column if not exists trigger_source text,
    add column if not exists request_id text;

comment on column public.vetmo_sync_runs.trigger_source is
    'Источник запуска: admin-app, workflow_dispatch, manual';
comment on column public.vetmo_sync_runs.request_id is
    'Идентификатор запуска для трассировки';

create index if not exists vetmo_sync_runs_request_idx
    on public.vetmo_sync_runs (request_id);
