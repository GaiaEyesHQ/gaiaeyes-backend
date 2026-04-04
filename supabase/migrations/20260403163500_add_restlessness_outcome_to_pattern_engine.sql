alter table if exists marts.user_daily_outcomes
  add column if not exists restlessness_day boolean not null default false,
  add column if not exists restlessness_events integer not null default 0;

comment on column marts.user_daily_outcomes.restlessness_day is
  'True when restless, wired, or irritable symptoms were logged that day for canonical mood/reactivity pattern matching.';

comment on column marts.user_daily_outcomes.restlessness_events is
  'Count of restless, wired, or irritable symptom logs grouped into the canonical restlessness outcome.';
