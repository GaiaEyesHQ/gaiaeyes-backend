begin;

-- Internal, draft-only data. No grants to the Mac, REST clients or service_role.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'gaia_earthscope_writer_backend') then
    create role gaia_earthscope_writer_backend nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'gaia_earthscope_writer_preparer') then
    create role gaia_earthscope_writer_preparer nologin;
  end if;
end $$;

create table content.earthscope_writer_jobs (
  job_id text not null check (job_id ~ '^[a-z0-9][a-z0-9._-]{2,79}$'),
  job_version integer not null check (job_version between 1 and 999999),
  day date not null,
  intended_worker_id text not null,
  input_classification text not null check (input_classification in ('dated_production_facts', 'synthetic_review_fixture')),
  facts_packet jsonb not null check (jsonb_typeof(facts_packet) = 'object'),
  facts_sha256 text not null check (facts_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  deadline_at timestamptz not null,
  status text not null default 'queued' check (status in ('queued', 'claimed', 'returned', 'failed', 'expired')),
  claim_id text unique,
  claimed_at timestamptz,
  lease_expires_at timestamptz,
  outcome jsonb,
  outcome_sha256 text check (outcome_sha256 ~ '^[0-9a-f]{64}$'),
  acknowledgement_id text unique,
  completed_at timestamptz,
  failure_code text,
  primary key (job_id, job_version),
  unique (day, job_version),
  check (deadline_at > created_at and deadline_at <= created_at + interval '30 minutes'),
  check ((claim_id is null and claimed_at is null and lease_expires_at is null)
      or (claim_id is not null and claimed_at is not null and lease_expires_at > claimed_at and lease_expires_at <= deadline_at)),
  check ((outcome is null and outcome_sha256 is null and acknowledgement_id is null)
      or (outcome is not null and outcome_sha256 is not null and acknowledgement_id is not null and completed_at is not null)),
  check ((status in ('returned', 'failed')) = (acknowledgement_id is not null))
);
create index earthscope_writer_jobs_pending on content.earthscope_writer_jobs (intended_worker_id, created_at)
  where status in ('queued', 'claimed');

create table content.earthscope_writer_claim_requests (
  worker_id text not null,
  claim_request_id uuid not null,
  created_at timestamptz not null default now(),
  job_id text,
  job_version integer,
  primary key (worker_id, claim_request_id),
  foreign key (job_id, job_version) references content.earthscope_writer_jobs(job_id, job_version),
  check ((job_id is null) = (job_version is null))
);

alter table content.earthscope_writer_jobs enable row level security;
alter table content.earthscope_writer_claim_requests enable row level security;
revoke all on content.earthscope_writer_jobs, content.earthscope_writer_claim_requests
  from public, anon, authenticated, service_role, gaia_earthscope_writer_backend, gaia_earthscope_writer_preparer;
grant usage on schema content to gaia_earthscope_writer_backend, gaia_earthscope_writer_preparer;
grant select on content.earthscope_writer_jobs to gaia_earthscope_writer_backend;
grant update (status,claim_id,claimed_at,lease_expires_at,outcome,outcome_sha256,acknowledgement_id,completed_at,failure_code)
  on content.earthscope_writer_jobs to gaia_earthscope_writer_backend;
grant select, insert on content.earthscope_writer_claim_requests to gaia_earthscope_writer_backend;
grant select, insert on content.earthscope_writer_jobs to gaia_earthscope_writer_preparer;
grant update (status,completed_at,failure_code) on content.earthscope_writer_jobs to gaia_earthscope_writer_preparer;
create policy earthscope_writer_backend_jobs on content.earthscope_writer_jobs
  to gaia_earthscope_writer_backend using (true) with check (true);
create policy earthscope_writer_preparer_jobs on content.earthscope_writer_jobs
  to gaia_earthscope_writer_preparer using (true) with check (true);
create policy earthscope_writer_backend_claims on content.earthscope_writer_claim_requests
  to gaia_earthscope_writer_backend using (true) with check (true);

-- Deliberately no role membership, login credential, SECURITY DEFINER function,
-- public policy, mart grant or production writer modification. Apply narrowly
-- reviewed role membership and public-mart column grants to verified services.
commit;
