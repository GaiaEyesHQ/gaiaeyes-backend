begin;

-- The existing symptom event + episode remain the canonical clinical identity.
-- These composite keys let every additive migraine row prove that the episode,
-- onset event, and user belong together.
create unique index if not exists user_symptom_events_id_user_uidx
  on raw.user_symptom_events (id, user_id);

create unique index if not exists user_symptom_episodes_id_user_event_uidx
  on raw.user_symptom_episodes (id, user_id, symptom_event_id);

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname = 'user_symptom_episodes_event_owner_fkey'
       and conrelid = 'raw.user_symptom_episodes'::regclass
  ) then
    alter table raw.user_symptom_episodes
      add constraint user_symptom_episodes_event_owner_fkey
      foreign key (symptom_event_id, user_id)
      references raw.user_symptom_events (id, user_id)
      on delete cascade
      not valid;
  end if;
end
$$;

comment on constraint user_symptom_episodes_event_owner_fkey
  on raw.user_symptom_episodes is
  'Enforces event/user ownership for new writes. NOT VALID preserves any historical rows for a separate audited cleanup.';

create table if not exists raw.user_migraine_episode_details (
  episode_id uuid primary key,
  user_id uuid not null,
  symptom_event_id uuid not null,
  schema_version text not null default '1.0'
    check (schema_version = '1.0'),
  revision integer not null default 1
    check (revision >= 1),
  payload jsonb not null
    check (jsonb_typeof(payload) = 'object'),
  user_edited_at timestamptz,
  retained_after_import_reversal_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_migraine_episode_details_parent_fkey
    foreign key (episode_id, user_id, symptom_event_id)
    references raw.user_symptom_episodes (id, user_id, symptom_event_id)
    on delete cascade,
  constraint user_migraine_episode_details_payload_episode_check
    check (payload ->> 'episode_id' = episode_id::text),
  constraint user_migraine_episode_details_payload_event_check
    check (payload ->> 'symptom_event_id' = symptom_event_id::text),
  constraint user_migraine_episode_details_payload_code_check
    check (upper(payload ->> 'symptom_code') = 'MIGRAINE'),
  constraint user_migraine_episode_details_payload_schema_check
    check (payload ->> 'schema_version' = schema_version),
  constraint user_migraine_episode_details_payload_revision_check
    check ((payload #>> '{lifecycle,revision}')::integer = revision)
);

create unique index if not exists user_migraine_episode_details_owner_event_uidx
  on raw.user_migraine_episode_details (episode_id, user_id, symptom_event_id);

create index if not exists user_migraine_episode_details_user_updated_idx
  on raw.user_migraine_episode_details (user_id, updated_at desc);

comment on table raw.user_migraine_episode_details is
  'Versioned structured detail for a canonical migraine symptom episode. It never replaces or silently rewrites the onset event.';

create or replace function raw.validate_migraine_episode_detail_parent()
returns trigger
language plpgsql
set search_path = pg_catalog, raw
as $$
declare
  parent_code text;
  parent_started_at timestamptz;
  payload_started_at timestamptz;
begin
  select ep.symptom_code, ep.started_at
    into parent_code, parent_started_at
    from raw.user_symptom_episodes ep
   where ep.id = new.episode_id
     and ep.user_id = new.user_id
     and ep.symptom_event_id = new.symptom_event_id;

  if not found then
    raise exception 'migraine detail parent episode not found for user'
      using errcode = '23503';
  end if;

  if lower(parent_code) <> 'migraine' then
    raise exception 'structured migraine details require a migraine episode'
      using errcode = '23514';
  end if;

  begin
    payload_started_at := (new.payload #>> '{start,utc}')::timestamptz;
  exception
    when others then
      raise exception 'migraine detail payload requires start.utc'
        using errcode = '23514';
  end;

  if payload_started_at is distinct from parent_started_at then
    raise exception 'migraine detail start must match the canonical onset'
      using errcode = '23514';
  end if;

  new.updated_at := now();
  return new;
end
$$;

drop trigger if exists trg_validate_migraine_episode_detail_parent
  on raw.user_migraine_episode_details;
create trigger trg_validate_migraine_episode_detail_parent
before insert or update on raw.user_migraine_episode_details
for each row execute function raw.validate_migraine_episode_detail_parent();

create table if not exists raw.user_migraine_episode_detail_revisions (
  id uuid primary key default gen_random_uuid(),
  episode_id uuid not null,
  user_id uuid not null,
  symptom_event_id uuid not null,
  revision integer not null check (revision >= 1),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  change_kind text not null
    check (change_kind in ('created', 'user_edit', 'import_commit', 'import_reversal_retained')),
  source text not null,
  created_at timestamptz not null default now(),
  constraint user_migraine_episode_detail_revisions_parent_fkey
    foreign key (episode_id, user_id, symptom_event_id)
    references raw.user_migraine_episode_details (episode_id, user_id, symptom_event_id)
    on delete cascade,
  unique (episode_id, revision)
);

create index if not exists user_migraine_episode_detail_revisions_user_idx
  on raw.user_migraine_episode_detail_revisions (user_id, episode_id, revision desc);

comment on table raw.user_migraine_episode_detail_revisions is
  'Append-only audit snapshots written atomically with migraine detail changes.';

create table if not exists raw.user_migraine_import_runs (
  id uuid primary key,
  user_id uuid not null,
  source_provider text not null check (btrim(source_provider) <> ''),
  source_file_hash text not null
    check (source_file_hash ~ '^[0-9a-f]{64}$'),
  mapping_version text not null check (btrim(mapping_version) <> ''),
  status text not null default 'preview'
    check (status in ('preview', 'committed', 'reversed')),
  created_at timestamptz not null default now(),
  committed_at timestamptz,
  reversed_at timestamptz,
  constraint user_migraine_import_runs_status_time_check check (
    (status = 'preview' and committed_at is null and reversed_at is null)
    or (status = 'committed' and committed_at is not null and reversed_at is null)
    or (status = 'reversed' and committed_at is not null and reversed_at is not null)
  ),
  unique (id, user_id)
);

create index if not exists user_migraine_import_runs_user_created_idx
  on raw.user_migraine_import_runs (user_id, created_at desc);

comment on table raw.user_migraine_import_runs is
  'Provider-neutral preview/commit/reversal lifecycle. A run or file hash is provenance, not clinical episode identity.';

create table if not exists raw.user_migraine_import_identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  source_provider text not null check (btrim(source_provider) <> ''),
  source_identity_key text not null check (btrim(source_identity_key) <> ''),
  episode_id uuid not null,
  symptom_event_id uuid not null,
  first_external_event_id text,
  canonical_origin_import_run_id uuid,
  canonical_origin_proof text
    check (canonical_origin_proof in ('canonical_sources_match_run')),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  constraint user_migraine_import_identities_episode_fkey
    foreign key (episode_id, user_id, symptom_event_id)
    references raw.user_symptom_episodes (id, user_id, symptom_event_id)
    on delete cascade,
  constraint user_migraine_import_identities_origin_run_fkey
    foreign key (canonical_origin_import_run_id, user_id)
    references raw.user_migraine_import_runs (id, user_id),
  constraint user_migraine_import_identities_origin_proof_check check (
    (canonical_origin_import_run_id is null and canonical_origin_proof is null)
    or (canonical_origin_import_run_id is not null and canonical_origin_proof is not null)
  ),
  unique (user_id, source_provider, source_identity_key),
  unique (user_id, source_provider, source_identity_key, episode_id, symptom_event_id)
);

create index if not exists user_migraine_import_identities_episode_idx
  on raw.user_migraine_import_identities (user_id, episode_id);

comment on table raw.user_migraine_import_identities is
  'Durable provider-neutral clinical identity mapping. It survives individual import-run reversal when the canonical episode is retained.';

comment on column raw.user_migraine_import_identities.canonical_origin_import_run_id is
  'Positive import-ownership evidence, set only when both canonical onset rows use the exact import:<run-id> source. NULL means reversal must preserve the canonical episode.';

create table if not exists raw.user_migraine_episode_import_links (
  id uuid primary key default gen_random_uuid(),
  import_run_id uuid not null,
  user_id uuid not null,
  episode_id uuid not null,
  symptom_event_id uuid not null,
  source_provider text not null check (btrim(source_provider) <> ''),
  external_event_id text not null check (btrim(external_event_id) <> ''),
  source_identity_key text not null check (btrim(source_identity_key) <> ''),
  source_file_hash text not null
    check (source_file_hash ~ '^[0-9a-f]{64}$'),
  raw_row_ref text not null check (btrim(raw_row_ref) <> ''),
  mapping_version text not null check (btrim(mapping_version) <> ''),
  linked_at timestamptz not null default now(),
  constraint user_migraine_episode_import_links_run_fkey
    foreign key (import_run_id, user_id)
    references raw.user_migraine_import_runs (id, user_id)
    on delete cascade,
  constraint user_migraine_episode_import_links_episode_fkey
    foreign key (episode_id, user_id, symptom_event_id)
    references raw.user_symptom_episodes (id, user_id, symptom_event_id)
    on delete cascade,
  constraint user_migraine_episode_import_links_identity_fkey
    foreign key (user_id, source_provider, source_identity_key, episode_id, symptom_event_id)
    references raw.user_migraine_import_identities
      (user_id, source_provider, source_identity_key, episode_id, symptom_event_id)
    on delete cascade,
  unique (user_id, import_run_id, source_provider, raw_row_ref),
  unique (user_id, import_run_id, source_provider, source_identity_key)
);

create index if not exists user_migraine_episode_import_links_identity_idx
  on raw.user_migraine_episode_import_links
  (user_id, source_provider, source_identity_key, linked_at desc);

create index if not exists user_migraine_episode_import_links_episode_idx
  on raw.user_migraine_episode_import_links (user_id, episode_id);

comment on column raw.user_migraine_episode_import_links.source_identity_key is
  'Stable provider event ID or reviewed clinical fingerprint. It must not be derived only from import run ID or file hash.';

alter table raw.user_migraine_episode_details enable row level security;
alter table raw.user_migraine_episode_detail_revisions enable row level security;
alter table raw.user_migraine_import_runs enable row level security;
alter table raw.user_migraine_import_identities enable row level security;
alter table raw.user_migraine_episode_import_links enable row level security;

drop policy if exists p_migraine_episode_details_select on raw.user_migraine_episode_details;
create policy p_migraine_episode_details_select
on raw.user_migraine_episode_details for select to authenticated
using (auth.uid() = user_id);

drop policy if exists p_migraine_episode_detail_revisions_select on raw.user_migraine_episode_detail_revisions;
create policy p_migraine_episode_detail_revisions_select
on raw.user_migraine_episode_detail_revisions for select to authenticated
using (auth.uid() = user_id);

drop policy if exists p_migraine_import_runs_select on raw.user_migraine_import_runs;
create policy p_migraine_import_runs_select
on raw.user_migraine_import_runs for select to authenticated
using (auth.uid() = user_id);

drop policy if exists p_migraine_import_identities_select on raw.user_migraine_import_identities;
create policy p_migraine_import_identities_select
on raw.user_migraine_import_identities for select to authenticated
using (auth.uid() = user_id);

drop policy if exists p_migraine_episode_import_links_select on raw.user_migraine_episode_import_links;
create policy p_migraine_episode_import_links_select
on raw.user_migraine_episode_import_links for select to authenticated
using (auth.uid() = user_id);

revoke all on table raw.user_migraine_episode_details from anon, authenticated;
revoke all on table raw.user_migraine_episode_detail_revisions from anon, authenticated;
revoke all on table raw.user_migraine_import_runs from anon, authenticated;
revoke all on table raw.user_migraine_import_identities from anon, authenticated;
revoke all on table raw.user_migraine_episode_import_links from anon, authenticated;

-- Authenticated clients may inspect their own rows when a reviewed consumer
-- exposes raw schema access. All mutations stay behind the backend repository
-- so revision checks and audit writes cannot be bypassed.
grant select
  on table raw.user_migraine_episode_details to authenticated;
grant select
  on table raw.user_migraine_episode_detail_revisions to authenticated;
grant select
  on table raw.user_migraine_import_runs to authenticated;
grant select
  on table raw.user_migraine_import_identities to authenticated;
grant select
  on table raw.user_migraine_episode_import_links to authenticated;

commit;
