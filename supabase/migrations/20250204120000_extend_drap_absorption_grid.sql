begin;

alter table if exists ext.drap_absorption
    add column if not exists lat numeric,
    add column if not exists lon numeric,
    add column if not exists lat_key text generated always as (coalesce(lat::text, 'na')) stored,
    add column if not exists lon_key text generated always as (coalesce(lon::text, 'na')) stored;

alter table if exists ext.drap_absorption
    drop constraint if exists drap_absorption_pkey;

alter table if exists ext.drap_absorption
    add constraint drap_absorption_pkey primary key (
        ts_utc,
        region_key,
        frequency_key,
        lat_key,
        lon_key
    );

commit;
