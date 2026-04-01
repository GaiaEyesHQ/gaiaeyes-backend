begin;

alter table if exists app.user_experience_profiles
  add column if not exists temp_unit text not null default 'F';

update app.user_experience_profiles
   set temp_unit = coalesce(nullif(upper(trim(temp_unit)), ''), 'F');

do $$
declare
  rec record;
begin
  for rec in
    select conname
      from pg_constraint
     where conrelid = 'app.user_experience_profiles'::regclass
       and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%temp_unit%'
  loop
    execute format('alter table app.user_experience_profiles drop constraint %I', rec.conname);
  end loop;
end $$;

alter table app.user_experience_profiles
  add constraint user_experience_profiles_temp_unit_check
  check (temp_unit in ('F', 'C'));

do $$
declare
  rec record;
begin
  for rec in
    select conname
      from pg_constraint
     where conrelid = 'app.user_experience_profiles'::regclass
       and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%onboarding_step%'
  loop
    execute format('alter table app.user_experience_profiles drop constraint %I', rec.conname);
  end loop;
end $$;

alter table app.user_experience_profiles
  add constraint user_experience_profiles_onboarding_step_check
  check (
    onboarding_step in (
      'welcome',
      'mode',
      'guide',
      'tone',
      'temperature_unit',
      'sensitivities',
      'health_context',
      'location',
      'healthkit',
      'backfill',
      'notifications',
      'activation'
    )
  );

commit;
