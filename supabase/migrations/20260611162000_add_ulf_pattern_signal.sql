begin;

alter table if exists marts.user_daily_features
    add column if not exists ulf_exposed boolean;

comment on column marts.user_daily_features.ulf_exposed is
  'True when usable ULF context is active, elevated, strong, or otherwise high-intensity enough for personal pattern comparison.';

commit;
