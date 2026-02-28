create table if not exists marts.user_gauges_delta_day (
  user_id uuid not null,
  day date not null,
  deltas_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, day)
);

alter table marts.user_gauges_delta_day enable row level security;

drop policy if exists "user_gauges_delta_day_select_own" on marts.user_gauges_delta_day;
create policy "user_gauges_delta_day_select_own"
  on marts.user_gauges_delta_day for select
  using (auth.uid() = user_id);
