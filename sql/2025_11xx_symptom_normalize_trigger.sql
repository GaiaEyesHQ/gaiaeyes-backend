-- Optional safeguard to keep raw.user_symptom_events normalized.
-- This script only creates the trigger function. Enable the trigger manually in
-- Supabase Studio (SQL editor) once you are ready.
-- Canonical dim.symptom_codes keys are lowercase snake_case, so the trigger must
-- preserve that casing to avoid foreign-key failures.

begin;

create schema if not exists raw;

create or replace function raw.tg_normalize_symptom_code()
returns trigger
language plpgsql
as $$
begin
    new.symptom_code := lower(replace(replace(new.symptom_code, '-', '_'), ' ', '_'));
    return new;
end;
$$;

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
end;
$$;

drop function if exists raw.upcase_symptom_code();

-- To enable the trigger, run the statement below in Supabase Studio after
-- reviewing:
-- create trigger trg_normalize_symptom_code
--     before insert or update
--     on raw.user_symptom_events
--     for each row
--     execute function raw.tg_normalize_symptom_code();

commit;
