-- VETMO 0.2 — дневные корзины OpenDota для скользящего окна 7 дней.
--
-- OpenDota /heroStats отдаёт:
--   pub_pick / pub_win                 — сумма за последние 7 дней;
--   pub_pick_trend / pub_win_trend     — те же значения по дням.
--
-- Сумма trend-массивов равна pub_pick/pub_win. Храним дневные
-- инкременты, чтобы окно можно было пересчитать на любую дату,
-- восстановить пропущенный синк и показать изменение день-к-дню.

create table if not exists public.vetmo_hero_daily (
    stat_date    date not null,
    patch_id     bigint not null references public.vetmo_patches(id) on delete cascade,
    hero_id      integer not null references public.vetmo_heroes(id) on delete cascade,
    rank_tier    smallint not null default 0 check (rank_tier between 0 and 8),
    position     smallint not null default 0 check (position between 0 and 5),
    game_mode    text not null default 'ALL_PICK_RANKED',
    match_count  integer not null default 0 check (match_count >= 0),
    win_count    integer not null default 0 check (win_count >= 0),
    source       text not null default 'opendota',
    updated_at   timestamptz not null default now(),
    primary key (stat_date, patch_id, hero_id, rank_tier, position, game_mode)
);

create index if not exists vetmo_hero_daily_lookup_idx
    on public.vetmo_hero_daily (stat_date, patch_id, rank_tier, position, game_mode);

create index if not exists vetmo_hero_daily_hero_idx
    on public.vetmo_hero_daily (hero_id, stat_date);

alter table public.vetmo_hero_daily enable row level security;

drop policy if exists vetmo_hero_daily_read on public.vetmo_hero_daily;
create policy vetmo_hero_daily_read on public.vetmo_hero_daily
    for select to anon, authenticated using (true);

grant select on public.vetmo_hero_daily to anon, authenticated;

-- Чистим и дневные корзины, чтобы таблица не росла бесконечно.
create or replace function public.vetmo_prune_old_data(p_days integer default 90)
returns void
language sql
security definer
set search_path = public
as $$
    delete from public.vetmo_snapshots
    where snapshot_date < current_date - greatest(1, p_days);

    delete from public.vetmo_hero_daily
    where stat_date < current_date - greatest(1, p_days);
$$;

revoke all on function public.vetmo_prune_old_data(integer) from public, anon, authenticated;
grant execute on function public.vetmo_prune_old_data(integer) to service_role;

-- PostgREST должен увидеть новую таблицу сразу после применения миграции.
notify pgrst, 'reload schema';
