-- Space visuals telemetry + overlay support
-- Adds telemetry/metadata columns and an upsert key for ext.space_visuals.

alter table if exists ext.space_visuals
    add column if not exists asset_type text,
    add column if not exists series jsonb,
    add column if not exists feature_flags jsonb,
    add column if not exists instrument text,
    add column if not exists credit text,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists updated_at timestamptz not null default now();

update ext.space_visuals
   set asset_type = 'image'
 where asset_type is null;

alter table if exists ext.space_visuals
    alter column asset_type set default 'image',
    alter column asset_type set not null;

create unique index if not exists ext_space_visuals_asset_key_ts_idx
    on ext.space_visuals (key, asset_type, ts);

create or replace function ext.space_visuals_touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    if new.created_at is null then
        new.created_at = now();
    end if;
    return new;
end;
$$ language plpgsql;

drop trigger if exists space_visuals_set_updated_at on ext.space_visuals;
create trigger space_visuals_set_updated_at
before insert or update on ext.space_visuals
for each row execute function ext.space_visuals_touch_updated_at();
