-- Optional safeguard to keep raw.user_symptom_events normalized.
-- This script only creates the trigger function. Enable the trigger manually in
-- Supabase Studio (SQL editor) once you are ready.

begin;

create schema if not exists raw;

create or replace function raw.tg_normalize_symptom_code()
returns trigger
language plpgsql
as $$
begin
    new.symptom_code := upper(replace(replace(new.symptom_code, '-', '_'), ' ', '_'));
    return new;
end;
$$;

drop trigger if exists trg_normalize_symptom_code on raw.user_symptom_events;

-- To enable the trigger, run the statement below in Supabase Studio after
-- reviewing:
-- create trigger trg_normalize_symptom_code
--     before insert or update
--     on raw.user_symptom_events
--     for each row
--     execute function raw.tg_normalize_symptom_code();

commit;
