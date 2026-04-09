begin;

alter table if exists marts.user_daily_features
    add column if not exists humidity_extreme_exposed boolean;

comment on column marts.user_daily_features.humidity_extreme_exposed is
  'True when daily humidity reaches a muggy or dry threshold likely to be noticeable in local context.';

commit;
