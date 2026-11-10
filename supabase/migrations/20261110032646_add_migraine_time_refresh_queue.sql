begin;
create table if not exists raw.migraine_time_refresh_users (
  user_id uuid primary key,
  generation bigint not null default 0 check (generation >= 0),
  progress_generation bigint not null default 0,
  completed_days date[] not null default '{}',
  writer_epoch bigint not null default 0 check (writer_epoch >= 0),
  lease_token uuid,
  lease_until timestamptz,
  updated_at timestamptz not null default now(),
  check ((lease_token is null) = (lease_until is null))
);
create table if not exists raw.migraine_time_refresh_jobs (
  user_id uuid not null,
  request_id uuid not null,
  episode_id uuid not null,
  generation bigint not null check (generation > 0),
  refresh_days date[] not null check (cardinality(refresh_days) > 0),
  pattern_since_day date not null,
  status text not null default 'pending' check (status in ('pending','running','complete','blocked')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  lease_token uuid,
  last_error_class text,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  primary key(user_id,request_id),
  foreign key(user_id) references raw.migraine_time_refresh_users(user_id),
  foreign key(episode_id) references raw.user_migraine_episode_details(episode_id) on delete cascade
);
create index if not exists migraine_time_refresh_jobs_ready_idx
  on raw.migraine_time_refresh_jobs(available_at,user_id) where status <> 'complete';
alter table raw.migraine_time_refresh_users enable row level security;
alter table raw.migraine_time_refresh_jobs enable row level security;
revoke all on raw.migraine_time_refresh_users,raw.migraine_time_refresh_jobs from public,anon,authenticated;
grant select,insert,update,delete on raw.migraine_time_refresh_users,raw.migraine_time_refresh_jobs to service_role;

-- Recover all existing receipts without altering canonical records or audit payloads.
-- Per-user lock/order derives stable generations on the first migration execution.
insert into raw.migraine_time_refresh_users(user_id,generation)
select user_id,count(*) from raw.user_migraine_episode_detail_revisions
where correction_request_id is not null and time_correction is not null group by user_id
on conflict(user_id) do nothing;
insert into raw.migraine_time_refresh_jobs(user_id,request_id,episode_id,generation,refresh_days,pattern_since_day)
select user_id,correction_request_id,episode_id,
       row_number() over(partition by user_id order by created_at,id),
       array(select value::date from jsonb_array_elements_text(time_correction->'refresh_days')),
       (time_correction->>'pattern_since_day')::date
from raw.user_migraine_episode_detail_revisions
where correction_request_id is not null and time_correction is not null
on conflict(user_id,request_id) do nothing;
comment on table raw.migraine_time_refresh_jobs is 'Durable derivative work only. Canonical correction receipts remain in the existing audit table.';
commit;
