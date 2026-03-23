-- If the optional raw.user_symptom_events normalization trigger was enabled
-- manually, ensure it preserves the canonical lowercase snake_case keys used by
-- dim.symptom_codes.

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
