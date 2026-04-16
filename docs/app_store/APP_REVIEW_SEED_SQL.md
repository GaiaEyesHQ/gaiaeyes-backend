# App Review Account Seed SQL

Use this from the Supabase SQL Editor to seed the App Review account with recent review/demo data copied from a source test account.

Do not use a personally sensitive source account unless you are comfortable with Apple reviewers seeing the copied HealthKit-derived values, symptoms, and pattern context. The script intentionally does not copy profile identity fields, free-text symptom notes, daily check-in notes, or exposure notes.

## Usage

1. Confirm `appreview@gaiaeyes.com` exists in Supabase Auth and is Plus-enabled.
2. Replace `REPLACE_WITH_SOURCE_EMAIL` with the source test account email.
3. Run the SQL block below in Supabase SQL Editor.
4. Open the app as `appreview@gaiaeyes.com`, pull to refresh Home/Body/Patterns/Outlook, and verify data appears.

```sql
begin;

create or replace function pg_temp.copy_review_seed_rows(
  p_table regclass,
  p_source_user uuid,
  p_target_user uuid,
  p_filter_column text,
  p_since_ts timestamptz,
  p_since_day date,
  p_ts_shift interval,
  p_day_shift integer,
  p_exclude_columns text[] default array[]::text[],
  p_null_columns text[] default array[]::text[]
) returns integer
language plpgsql
as $$
declare
  v_table_name text;
  v_filter_type text;
  v_columns text;
  v_values text;
  v_where text;
  v_sql text;
  v_rows integer := 0;
begin
  select quote_ident(n.nspname) || '.' || quote_ident(c.relname)
    into v_table_name
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where c.oid = p_table;

  select format_type(a.atttypid, a.atttypmod)
    into v_filter_type
    from pg_attribute a
   where a.attrelid = p_table
     and a.attname = p_filter_column
     and a.attnum > 0
     and not a.attisdropped;

  select
    string_agg(quote_ident(a.attname), ', ' order by a.attnum),
    string_agg(
      case
        when a.attname = 'user_id' then quote_literal(p_target_user)::text || '::uuid'
        when a.attname = any(p_null_columns) then 'null'
        when format_type(a.atttypid, a.atttypmod) in ('timestamp with time zone', 'timestamp without time zone')
          then case
            when a.attname in ('created_at', 'updated_at', 'ingested_at') then 'now()'
            else quote_ident(a.attname) || ' + ' || quote_literal(p_ts_shift)::text || '::interval'
          end
        when format_type(a.atttypid, a.atttypmod) = 'date'
          then quote_ident(a.attname) || ' + ' || p_day_shift::text
        else quote_ident(a.attname)
      end,
      ', ' order by a.attnum
    )
    into v_columns, v_values
    from pg_attribute a
   where a.attrelid = p_table
     and a.attnum > 0
     and not a.attisdropped
     and a.attidentity = ''
     and a.attgenerated = ''
     and not (a.attname = any(p_exclude_columns));

  if p_filter_column is null then
    v_where := format('where user_id = %L::uuid', p_source_user);
  elsif v_filter_type = 'date' then
    v_where := format(
      'where user_id = %L::uuid and %I >= %L::date',
      p_source_user,
      p_filter_column,
      p_since_day
    );
  else
    v_where := format(
      'where user_id = %L::uuid and %I >= %L::timestamptz',
      p_source_user,
      p_filter_column,
      p_since_ts
    );
  end if;

  v_sql := format(
    'insert into %s (%s) select %s from %s %s',
    v_table_name,
    v_columns,
    v_values,
    v_table_name,
    v_where
  );

  execute v_sql;
  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

do $$
declare
  v_source_email text := lower('REPLACE_WITH_SOURCE_EMAIL');
  v_target_email text := lower('appreview@gaiaeyes.com');
  v_days integer := 60;
  v_source_user uuid;
  v_target_user uuid;
  v_anchor_ts timestamptz;
  v_anchor_day date;
  v_local_today date := (timezone('America/Chicago', now()))::date;
  v_since_ts timestamptz;
  v_since_day date;
  v_ts_shift interval;
  v_day_shift integer;
  v_rows integer;
begin
  select id into v_source_user
    from auth.users
   where lower(email) = v_source_email
   limit 1;

  select id into v_target_user
    from auth.users
   where lower(email) = v_target_email
   limit 1;

  if v_source_user is null then
    raise exception 'Source user not found for email %', v_source_email;
  end if;

  if v_target_user is null then
    raise exception 'Target user not found for email %', v_target_email;
  end if;

  if v_source_user = v_target_user then
    raise exception 'Source and target users are the same account';
  end if;

  select max(ts) into v_anchor_ts
    from (
      select max(start_time) as ts from gaia.samples where user_id = v_source_user
      union all
      select max(ts_utc) as ts from raw.user_symptom_events where user_id = v_source_user
      union all
      select max(event_ts_utc) as ts from raw.user_exposure_events where user_id = v_source_user
      union all
      select max(completed_at) as ts from raw.user_daily_checkins where user_id = v_source_user
    ) anchors;

  if v_anchor_ts is null then
    raise exception 'Source user has no seedable sample/symptom/check-in data';
  end if;

  v_anchor_day := (timezone('America/Chicago', v_anchor_ts))::date;
  v_since_ts := v_anchor_ts - make_interval(days => v_days);
  v_since_day := v_anchor_day - v_days;
  v_ts_shift := now() - v_anchor_ts;
  v_day_shift := v_local_today - v_anchor_day;

  insert into gaia.users (id)
  values (v_target_user)
  on conflict (id) do nothing;

  -- Clear only the review account's recent/demo window so the script is safe to rerun.
  delete from raw.user_exposure_events
   where user_id = v_target_user
     and event_ts_utc >= now() - interval '75 days';

  delete from raw.user_daily_checkins
   where user_id = v_target_user
     and day >= v_local_today - 75;

  delete from raw.user_symptom_events
   where user_id = v_target_user
     and ts_utc >= now() - interval '75 days';

  delete from gaia.samples
   where user_id = v_target_user
     and start_time >= now() - interval '75 days';

  delete from gaia.daily_summary
   where user_id = v_target_user
     and date >= v_local_today - 75;

  delete from marts.user_daily_features
   where user_id = v_target_user
     and day >= v_local_today - 75;

  delete from marts.user_daily_outcomes
   where user_id = v_target_user
     and day >= v_local_today - 75;

  delete from marts.user_pattern_associations
   where user_id = v_target_user;

  v_rows := pg_temp.copy_review_seed_rows(
    'gaia.samples'::regclass,
    v_source_user,
    v_target_user,
    'start_time',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift,
    array['id']::text[],
    array[]::text[]
  );
  raise notice 'Copied % gaia.samples rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'raw.user_symptom_events'::regclass,
    v_source_user,
    v_target_user,
    'ts_utc',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift,
    array['id']::text[],
    array['free_text']::text[]
  );
  raise notice 'Copied % raw.user_symptom_events rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'raw.user_exposure_events'::regclass,
    v_source_user,
    v_target_user,
    'event_ts_utc',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift,
    array['id']::text[],
    array['note_text']::text[]
  );
  raise notice 'Copied % raw.user_exposure_events rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'raw.user_daily_checkins'::regclass,
    v_source_user,
    v_target_user,
    'day',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift,
    array['prompt_id']::text[],
    array['note_text']::text[]
  );
  raise notice 'Copied % raw.user_daily_checkins rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'gaia.daily_summary'::regclass,
    v_source_user,
    v_target_user,
    'date',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift
  );
  raise notice 'Copied % gaia.daily_summary rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'marts.user_daily_features'::regclass,
    v_source_user,
    v_target_user,
    'day',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift
  );
  raise notice 'Copied % marts.user_daily_features rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'marts.user_daily_outcomes'::regclass,
    v_source_user,
    v_target_user,
    'day',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift
  );
  raise notice 'Copied % marts.user_daily_outcomes rows', v_rows;

  v_rows := pg_temp.copy_review_seed_rows(
    'marts.user_pattern_associations'::regclass,
    v_source_user,
    v_target_user,
    'last_outcome_day',
    v_since_ts,
    v_since_day,
    v_ts_shift,
    v_day_shift
  );
  raise notice 'Copied % marts.user_pattern_associations rows', v_rows;

  raise notice 'Seed complete. Source %, target %, shifted % days / % interval.',
    v_source_user,
    v_target_user,
    v_day_shift,
    v_ts_shift;
end;
$$;

commit;
```

## Optional validation queries

```sql
select
  u.email,
  (select count(*) from gaia.samples s where s.user_id = u.id and s.start_time >= now() - interval '75 days') as samples_75d,
  (select count(*) from raw.user_symptom_events e where e.user_id = u.id and e.ts_utc >= now() - interval '75 days') as symptoms_75d,
  (select count(*) from raw.user_daily_checkins c where c.user_id = u.id and c.day >= (timezone('America/Chicago', now()))::date - 75) as checkins_75d,
  (select count(*) from raw.user_exposure_events x where x.user_id = u.id and x.event_ts_utc >= now() - interval '75 days') as exposures_75d,
  (select count(*) from marts.user_pattern_associations p where p.user_id = u.id and p.surfaceable) as surfaceable_patterns
from auth.users u
where lower(u.email) = lower('appreview@gaiaeyes.com');
```
