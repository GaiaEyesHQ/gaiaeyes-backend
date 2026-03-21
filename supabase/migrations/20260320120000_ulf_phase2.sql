create schema if not exists marts;

create table if not exists marts.ulf_activity_5m (
  station_id text not null,
  ts_utc timestamptz not null,
  window_seconds integer not null default 300,
  component_used text not null,
  component_substituted boolean not null default false,

  dbdt_rms double precision,
  ulf_rms_broad double precision,
  ulf_band_proxy double precision,

  ulf_index_station double precision,
  ulf_index_localtime double precision,

  persistence_30m double precision,
  persistence_90m double precision,

  quality_flags jsonb not null default '[]'::jsonb,
  source text not null default 'usgs',
  created_at timestamptz not null default now(),

  primary key (station_id, ts_utc)
);

create index if not exists idx_ulf_activity_5m_ts
  on marts.ulf_activity_5m (ts_utc desc);

create index if not exists idx_ulf_activity_5m_station_ts
  on marts.ulf_activity_5m (station_id, ts_utc desc);

create table if not exists marts.ulf_context_5m (
  ts_utc timestamptz not null primary key,
  stations_used text[] not null default '{}',

  regional_intensity double precision,
  regional_coherence double precision,
  regional_persistence double precision,

  context_class text,
  confidence_score double precision,

  quality_flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_ulf_context_5m_ts
  on marts.ulf_context_5m (ts_utc desc);
