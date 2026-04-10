begin;

create schema if not exists app;

create table if not exists app.user_bug_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  source text not null default 'ios_app',
  description text not null,
  diagnostics_bundle text not null,
  app_version text null,
  device text null,
  alert_sent boolean not null default false,
  alert_error text null,
  created_at timestamptz not null default now()
);

create index if not exists idx_user_bug_reports_user_created_at
  on app.user_bug_reports (user_id, created_at desc);

alter table app.user_bug_reports enable row level security;

drop policy if exists p_user_bug_reports_select on app.user_bug_reports;
create policy p_user_bug_reports_select
on app.user_bug_reports
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_bug_reports_insert on app.user_bug_reports;
create policy p_user_bug_reports_insert
on app.user_bug_reports
for insert
to authenticated
with check (auth.uid() = user_id);

commit;
