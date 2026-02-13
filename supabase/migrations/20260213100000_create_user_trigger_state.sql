create schema if not exists app;

create table if not exists app.user_trigger_state (
  user_id uuid not null,
  trigger_key text not null,
  last_sent_at timestamptz null,
  last_severity text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, trigger_key)
);

alter table app.user_trigger_state enable row level security;

drop policy if exists p_user_trigger_state_select on app.user_trigger_state;
create policy p_user_trigger_state_select
on app.user_trigger_state
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_trigger_state_insert on app.user_trigger_state;
create policy p_user_trigger_state_insert
on app.user_trigger_state
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_trigger_state_update on app.user_trigger_state;
create policy p_user_trigger_state_update
on app.user_trigger_state
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
