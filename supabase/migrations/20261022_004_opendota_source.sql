-- VETMO — поддержка нескольких источников мета-данных (OpenDota + STRATZ).
-- Добавляет индекс по колонке source для быстрой фильтрации и одинаковую
-- структуру delta-колонок в snapshots для совместимости.

create index if not exists vetmo_meta_source_idx
    on public.vetmo_meta (source, patch_id, rank_tier, position, window_days);

create index if not exists vetmo_snapshots_source_idx
    on public.vetmo_snapshots (source, patch_id, rank_tier, position, window_days);

-- src/vetmo/services/supabase_meta.py пишет source='opendota' или 'stratz'.
-- Старые строки без source уже имеют дефолт 'stratz' из миграции 001.
