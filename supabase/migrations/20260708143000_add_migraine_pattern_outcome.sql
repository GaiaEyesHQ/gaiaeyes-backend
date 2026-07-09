-- Add migraine as a first-class symptom and pattern outcome while keeping headache distinct.

insert into dim.symptom_codes as sc (symptom_code, label, description)
values
  ('migraine', 'Migraine', 'Migraine attack, aura, light sensitivity, or migraine-specific head pain')
on conflict (symptom_code) do update
set label = excluded.label,
    description = excluded.description,
    is_active = true;

update dim.symptom_codes
   set description = 'Headache, head pain, or pressure'
 where symptom_code = 'headache';

alter table if exists marts.user_daily_features
  add column if not exists migraine_symptom_events integer not null default 0;

alter table if exists marts.user_daily_outcomes
  add column if not exists migraine_day boolean not null default false,
  add column if not exists migraine_events integer not null default 0;
