-- If the optional raw.user_symptom_events normalization trigger was enabled
-- manually, remove it. The API now resolves to canonical dim.symptom_codes
-- values before insert, and the legacy trigger can corrupt casing and break the
-- foreign-key constraint.

create schema if not exists raw;

do $$
declare
  trigger_name text;
begin
  for trigger_name in
    select tgname
    from pg_trigger
    where tgrelid = 'raw.user_symptom_events'::regclass
      and not tgisinternal
  loop
    execute format('drop trigger if exists %I on raw.user_symptom_events', trigger_name);
  end loop;
end
$$;

drop function if exists raw.upcase_symptom_code();

create or replace function raw.tg_normalize_symptom_code()
returns trigger
language plpgsql
as $$
begin
  new.symptom_code := lower(replace(replace(new.symptom_code, '-', '_'), ' ', '_'));
  return new;
end;
$$;
