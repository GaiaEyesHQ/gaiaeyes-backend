create schema if not exists ext;

create table if not exists ext.zip_centroids (
    zip text primary key,
    lat double precision,
    lon double precision
);

create table if not exists ext.local_signals_cache (
    zip text not null,
    asof timestamptz not null,
    payload jsonb not null,
    expires_at timestamptz not null,
    primary key (zip, asof)
);

create index if not exists local_signals_cache_zip_expires_idx
    on ext.local_signals_cache (zip, expires_at desc);
