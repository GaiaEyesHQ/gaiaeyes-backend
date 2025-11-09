-- Aurora nowcast persistence (WordPress cron ingestion)
create table if not exists marts.aurora_nowcast_samples (
    ts timestamptz not null,
    hemisphere text not null check (hemisphere in ('north','south')),
    grid_width int not null,
    grid_height int not null,
    probabilities jsonb,
    kp numeric,
    kp_obs_time timestamptz,
    viewline_p numeric default 0.10,
    viewline_coords jsonb,
    source text default 'SWPC_OVATION',
    fetch_ms int,
    created_at timestamptz default now(),
    constraint aurora_nowcast_samples_pk primary key (ts, hemisphere)
);

create table if not exists marts.aurora_viewline_forecast (
    ts date primary key,
    tonight_url text,
    tomorrow_url text,
    tonight_etag text,
    tomorrow_etag text,
    fetch_ms int,
    updated_at timestamptz default now()
);

create table if not exists marts.kp_obs (
    kp_time timestamptz primary key,
    kp numeric,
    raw jsonb
);

comment on table marts.aurora_nowcast_samples is 'SWPC OVATION latest grid snapshots + derived viewlines (north/south).';
comment on table marts.aurora_viewline_forecast is 'Cached metadata for NOAA experimental viewline PNGs (tonight/tomorrow).';
comment on table marts.kp_obs is 'Last-observed planetary Kp index as ingested by WordPress cron.';
