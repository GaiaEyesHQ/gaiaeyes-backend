begin;

create schema if not exists app;

create table if not exists app.user_experience_profiles (
  user_id uuid primary key,
  mode text not null default 'scientific'
    check (mode in ('scientific', 'mystical')),
  guide text not null default 'cat'
    check (guide in ('cat', 'robot', 'dog')),
  tone text not null default 'balanced'
    check (tone in ('straight', 'balanced', 'humorous')),
  onboarding_step text not null default 'welcome'
    check (
      onboarding_step in (
        'welcome',
        'mode',
        'guide',
        'tone',
        'sensitivities',
        'health_context',
        'location',
        'healthkit',
        'backfill',
        'notifications',
        'activation'
      )
    ),
  onboarding_completed boolean not null default false,
  onboarding_completed_at timestamptz null,
  healthkit_requested_at timestamptz null,
  last_backfill_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table app.user_experience_profiles enable row level security;

drop policy if exists p_user_experience_profiles_select on app.user_experience_profiles;
create policy p_user_experience_profiles_select
on app.user_experience_profiles
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_experience_profiles_insert on app.user_experience_profiles;
create policy p_user_experience_profiles_insert
on app.user_experience_profiles
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_experience_profiles_update on app.user_experience_profiles;
create policy p_user_experience_profiles_update
on app.user_experience_profiles
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

commit;
