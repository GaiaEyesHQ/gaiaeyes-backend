insert into dim.symptom_codes as sc (symptom_code, label, description)
values
  ('migraine', 'Migraine', 'Migraine attack, aura, light sensitivity, or migraine-specific head pain')
on conflict (symptom_code) do update
set label = excluded.label,
    description = excluded.description,
    is_active = true;
