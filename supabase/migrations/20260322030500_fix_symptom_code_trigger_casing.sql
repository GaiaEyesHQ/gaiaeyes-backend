-- If the optional raw.user_symptom_events normalization trigger was enabled
-- manually, remove it. The API now resolves to canonical dim.symptom_codes
-- values before insert, and the legacy trigger can corrupt casing and break the
-- foreign-key constraint.

create schema if not exists raw;

drop trigger if exists trg_normalize_symptom_code on raw.user_symptom_events;

create or replace function raw.tg_normalize_symptom_code()
returns trigger
language plpgsql
as $$
begin
  new.symptom_code := lower(replace(replace(new.symptom_code, '-', '_'), ' ', '_'));
  return new;
end;
$$;
