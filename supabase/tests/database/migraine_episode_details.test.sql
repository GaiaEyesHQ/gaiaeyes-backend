begin;

create extension if not exists pgtap with schema extensions;
set search_path = extensions, public, raw, dim;

select plan(22);

select ok(to_regclass('raw.user_migraine_episode_details') is not null,
  'migraine detail table exists');
select ok(to_regclass('raw.user_migraine_episode_detail_revisions') is not null,
  'migraine detail revision table exists');
select ok(to_regclass('raw.user_migraine_import_runs') is not null,
  'migraine import run table exists');
select ok(to_regclass('raw.user_migraine_import_identities') is not null,
  'migraine import identity table exists');
select ok(to_regclass('raw.user_migraine_episode_import_links') is not null,
  'migraine import link table exists');
select ok(
  exists (
    select 1
      from information_schema.columns
     where table_schema = 'raw'
       and table_name = 'user_migraine_import_identities'
       and column_name = 'canonical_origin_import_run_id'
  ),
  'durable identity records positive canonical import ownership'
);
select ok(
  exists (
    select 1
      from information_schema.columns
     where table_schema = 'raw'
       and table_name = 'user_migraine_import_identities'
       and column_name = 'canonical_origin_proof'
  ),
  'durable identity records how canonical import ownership was proven'
);

insert into raw.user_symptom_events (
  id, user_id, ts_utc, symptom_code, severity, source
) values
  ('91000000-0000-4000-8000-000000000001', '90000000-0000-4000-8000-000000000001',
   '2026-09-01T14:00:00Z', 'migraine', 5, 'test'),
  ('92000000-0000-4000-8000-000000000001', '90000000-0000-4000-8000-000000000002',
   '2026-09-01T15:00:00Z', 'migraine', 4, 'test'),
  ('91000000-0000-4000-8000-000000000003', '90000000-0000-4000-8000-000000000001',
   '2026-09-02T14:00:00Z', 'migraine', 3, 'test');

insert into raw.user_symptom_episodes (
  id, user_id, symptom_event_id, symptom_code, started_at,
  original_severity, current_severity, source
) values
  ('93000000-0000-4000-8000-000000000001', '90000000-0000-4000-8000-000000000001',
   '91000000-0000-4000-8000-000000000001', 'migraine', '2026-09-01T14:00:00Z', 5, 5, 'test'),
  ('94000000-0000-4000-8000-000000000001', '90000000-0000-4000-8000-000000000002',
   '92000000-0000-4000-8000-000000000001', 'migraine', '2026-09-01T15:00:00Z', 4, 4, 'test'),
  ('93000000-0000-4000-8000-000000000003', '90000000-0000-4000-8000-000000000001',
   '91000000-0000-4000-8000-000000000003', 'migraine', '2026-09-02T14:00:00Z', 3, 3, 'test');

insert into raw.user_migraine_episode_details (
  episode_id, user_id, symptom_event_id, revision, payload
) values (
  '93000000-0000-4000-8000-000000000001',
  '90000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000001',
  1,
  jsonb_build_object(
    'schema_version', '1.0',
    'episode_id', '93000000-0000-4000-8000-000000000001',
    'symptom_event_id', '91000000-0000-4000-8000-000000000001',
    'symptom_code', 'MIGRAINE',
    'start', jsonb_build_object('utc', '2026-09-01T14:00:00Z'),
    'lifecycle', jsonb_build_object('revision', 1)
  )
);

insert into raw.user_migraine_episode_detail_revisions (
  episode_id, user_id, symptom_event_id, revision, payload, change_kind, source
)
select episode_id, user_id, symptom_event_id, revision, payload, 'created', 'test'
  from raw.user_migraine_episode_details;

insert into raw.user_migraine_import_runs (
  id, user_id, source_provider, source_file_hash, mapping_version,
  status, committed_at
) values (
  '95000000-0000-4000-8000-000000000001',
  '90000000-0000-4000-8000-000000000001',
  'synthetic', repeat('a', 64), 'test-1', 'committed', now()
);

insert into raw.user_migraine_import_identities (
  user_id, source_provider, source_identity_key, episode_id,
  symptom_event_id, first_external_event_id
) values (
  '90000000-0000-4000-8000-000000000001',
  'synthetic', 'stable-event-1',
  '93000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000001',
  'event-1'
);

insert into raw.user_migraine_episode_import_links (
  import_run_id, user_id, episode_id, symptom_event_id, source_provider,
  external_event_id, source_identity_key, source_file_hash, raw_row_ref,
  mapping_version
) values (
  '95000000-0000-4000-8000-000000000001',
  '90000000-0000-4000-8000-000000000001',
  '93000000-0000-4000-8000-000000000001',
  '91000000-0000-4000-8000-000000000001',
  'synthetic', 'event-1', 'stable-event-1', repeat('a', 64), 'row:1', 'test-1'
);

set local role authenticated;
select set_config('request.jwt.claim.sub', '90000000-0000-4000-8000-000000000001', true);

select is(
  (select count(*)::integer from raw.user_migraine_episode_details),
  1,
  'owner can read own migraine detail'
);

select throws_ok(
  $$update raw.user_migraine_episode_details
       set user_edited_at = now()
     where episode_id = '93000000-0000-4000-8000-000000000001'$$,
  '42501',
  null,
  'direct owner mutation is denied so backend revision and audit checks cannot be bypassed'
);

select is(
  (select count(*)::integer from raw.user_migraine_episode_detail_revisions),
  1,
  'owner can read own append-only audit'
);

select is(
  (select count(*)::integer from raw.user_migraine_import_runs),
  1,
  'owner can read own import run'
);

select is(
  (select count(*)::integer from raw.user_migraine_import_identities),
  1,
  'owner can read own durable import identity'
);

select is(
  (select count(*)::integer from raw.user_migraine_episode_import_links),
  1,
  'owner can read own import link'
);

select set_config('request.jwt.claim.sub', '90000000-0000-4000-8000-000000000002', true);

select is(
  (select count(*)::integer from raw.user_migraine_episode_details),
  0,
  'another authenticated user cannot read the detail'
);

select is(
  (select count(*)::integer from raw.user_migraine_episode_detail_revisions),
  0,
  'another authenticated user cannot read the audit'
);

select is(
  (select count(*)::integer from raw.user_migraine_import_runs),
  0,
  'another authenticated user cannot read the import run'
);

select is(
  (select count(*)::integer from raw.user_migraine_import_identities),
  0,
  'another authenticated user cannot read the durable import identity'
);

select is(
  (select count(*)::integer from raw.user_migraine_episode_import_links),
  0,
  'another authenticated user cannot read the import link'
);

select throws_ok(
  $$insert into raw.user_migraine_episode_details (
      episode_id, user_id, symptom_event_id, revision, payload
    ) values (
      '93000000-0000-4000-8000-000000000003',
      '90000000-0000-4000-8000-000000000001',
      '91000000-0000-4000-8000-000000000003',
      1,
      jsonb_build_object(
        'schema_version', '1.0',
        'episode_id', '93000000-0000-4000-8000-000000000003',
        'symptom_event_id', '91000000-0000-4000-8000-000000000003',
        'symptom_code', 'MIGRAINE',
        'start', jsonb_build_object('utc', '2026-09-02T14:00:00Z'),
        'lifecycle', jsonb_build_object('revision', 1)
      )
    )$$,
  '42501',
  null,
  'authenticated user cannot insert for another owner'
);

reset role;

delete from raw.user_migraine_episode_import_links
 where import_run_id = '95000000-0000-4000-8000-000000000001'
   and user_id = '90000000-0000-4000-8000-000000000001';

select is(
  (
    select count(*)::integer
      from raw.user_migraine_import_identities
     where user_id = '90000000-0000-4000-8000-000000000001'
       and source_provider = 'synthetic'
       and source_identity_key = 'stable-event-1'
  ),
  1,
  'durable identity remains independent of an individual run link'
);

select throws_ok(
  $$insert into raw.user_migraine_episode_details (
      episode_id, user_id, symptom_event_id, revision, payload
    ) values (
      '94000000-0000-4000-8000-000000000001',
      '90000000-0000-4000-8000-000000000001',
      '92000000-0000-4000-8000-000000000001',
      1,
      jsonb_build_object(
        'schema_version', '1.0',
        'episode_id', '94000000-0000-4000-8000-000000000001',
        'symptom_event_id', '92000000-0000-4000-8000-000000000001',
        'symptom_code', 'MIGRAINE',
        'start', jsonb_build_object('utc', '2026-09-01T15:00:00Z'),
        'lifecycle', jsonb_build_object('revision', 1)
      )
    )$$,
  '23503',
  null,
  'composite parent key prevents cross-account episode linkage'
);

set local role anon;
select throws_ok(
  $$select * from raw.user_migraine_episode_details$$,
  '42501',
  null,
  'anonymous role has no migraine detail privileges'
);

reset role;
select * from finish();
rollback;
