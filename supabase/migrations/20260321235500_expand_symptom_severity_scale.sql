do $$
declare
  r record;
begin
  for r in
    select c.conname
      from pg_constraint c
      join pg_class t
        on t.oid = c.conrelid
      join pg_namespace n
        on n.oid = t.relnamespace
     where c.contype = 'c'
       and n.nspname = 'raw'
       and t.relname = 'user_symptom_events'
       and pg_get_constraintdef(c.oid) ilike '%severity%'
  loop
    execute format(
      'alter table raw.user_symptom_events drop constraint %I',
      r.conname
    );
  end loop;
end
$$;

alter table if exists raw.user_symptom_events
  add constraint user_symptom_events_severity_check
  check (severity between 0 and 10);
