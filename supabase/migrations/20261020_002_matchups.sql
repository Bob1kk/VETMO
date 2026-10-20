-- VETMO — матчапы героев: контрпики, хорошие пики и связки.
-- Применять после 20261020_001_init.sql. Миграция идемпотентна.

alter table public.vetmo_hero_matchups
    add column if not exists kind text not null default 'vs',
    add column if not exists rank_bracket text not null default 'ALL',
    add column if not exists bucket text,
    add column if not exists bucket_rank smallint,
    add column if not exists sample_reliable boolean not null default true;

comment on column public.vetmo_hero_matchups.vs_hero_id is
    'Оппонент при kind=vs; союзник при kind=with (историческое имя колонки).';
comment on column public.vetmo_hero_matchups.rank_bracket is
    'ALL или группа STRATZ: HERALD_GUARDIAN, CRUSADER_ARCHON, LEGEND_ANCIENT, DIVINE_IMMORTAL.';
comment on column public.vetmo_hero_matchups.bucket is
    'NULL — полный ряд; counter/good/synergy — top-10 highlight.';

alter table public.vetmo_hero_matchups
    drop constraint if exists vetmo_hero_matchups_kind_check,
    drop constraint if exists vetmo_hero_matchups_bracket_check,
    drop constraint if exists vetmo_hero_matchups_bucket_check,
    drop constraint if exists vetmo_hero_matchups_bucket_rank_check,
    drop constraint if exists vetmo_hero_matchups_bucket_consistency;

alter table public.vetmo_hero_matchups
    add constraint vetmo_hero_matchups_kind_check
        check (kind in ('vs', 'with')),
    add constraint vetmo_hero_matchups_bracket_check
        check (rank_bracket in (
            'ALL', 'HERALD_GUARDIAN', 'CRUSADER_ARCHON',
            'LEGEND_ANCIENT', 'DIVINE_IMMORTAL'
        )),
    add constraint vetmo_hero_matchups_bucket_check
        check (bucket is null or bucket in ('counter', 'good', 'synergy')),
    add constraint vetmo_hero_matchups_bucket_rank_check
        check (bucket_rank is null or bucket_rank between 1 and 10),
    add constraint vetmo_hero_matchups_bucket_consistency
        check ((bucket is null) = (bucket_rank is null));

-- Ключ включает kind и rank_bracket: у героя несколько независимых срезов.
alter table public.vetmo_hero_matchups
    drop constraint if exists vetmo_hero_matchups_pkey;
alter table public.vetmo_hero_matchups
    add primary key (patch_id, hero_id, kind, rank_bracket, vs_hero_id);

create index if not exists vetmo_matchups_highlight_idx
    on public.vetmo_hero_matchups
    (patch_id, hero_id, rank_bracket, bucket, bucket_rank);

create or replace view public.v_vetmo_matchup_highlights as
select
    m.patch_id,
    p.version as patch_version,
    m.hero_id,
    h.localized_name as hero_name,
    m.rank_bracket,
    m.bucket,
    m.bucket_rank,
    m.kind,
    m.vs_hero_id as other_hero_id,
    o.localized_name as other_hero_name,
    m.win_rate,
    m.match_count,
    m.sample_reliable,
    m.updated_at
from public.vetmo_hero_matchups m
join public.vetmo_heroes h on h.id = m.hero_id
join public.vetmo_heroes o on o.id = m.vs_hero_id
join public.vetmo_patches p on p.id = m.patch_id
where m.bucket is not null;

alter view public.v_vetmo_matchup_highlights set (security_invoker = true);
grant select on public.v_vetmo_matchup_highlights to anon, authenticated;

-- PostgREST кэширует схему; без этого новые колонки дают PGRST204.
notify pgrst, 'reload schema';
