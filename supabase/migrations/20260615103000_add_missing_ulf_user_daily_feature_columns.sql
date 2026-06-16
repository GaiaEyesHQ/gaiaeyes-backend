begin;

alter table if exists marts.user_daily_features
  add column if not exists ulf_context_class_raw text,
  add column if not exists ulf_context_label text,
  add column if not exists ulf_confidence_score double precision,
  add column if not exists ulf_confidence_label text,
  add column if not exists ulf_regional_intensity double precision,
  add column if not exists ulf_regional_coherence double precision,
  add column if not exists ulf_regional_persistence double precision,
  add column if not exists ulf_quality_flags jsonb not null default '[]'::jsonb,
  add column if not exists ulf_is_provisional boolean not null default false,
  add column if not exists ulf_is_usable boolean not null default false,
  add column if not exists ulf_is_high_confidence boolean not null default false,
  add column if not exists ulf_station_count integer,
  add column if not exists ulf_missing_samples boolean not null default false,
  add column if not exists ulf_low_history boolean not null default false;

comment on column marts.user_daily_features.ulf_context_class_raw is
  'Raw ULF context class copied from the daily feature mart for personal pattern comparison.';

comment on column marts.user_daily_features.ulf_context_label is
  'Friendly ULF context label copied from the daily feature mart for personal pattern comparison.';

comment on column marts.user_daily_features.ulf_confidence_score is
  'ULF context confidence score available to the personal pattern engine.';

comment on column marts.user_daily_features.ulf_is_usable is
  'True when ULF context passed quality gates for personal pattern comparison.';

commit;
