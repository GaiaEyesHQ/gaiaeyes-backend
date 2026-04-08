begin;

alter table if exists app.user_experience_profiles
  add column if not exists tracked_stat_keys text[] not null default array['resting_hr', 'respiratory', 'hrv', 'spo2', 'steps']::text[],
  add column if not exists smart_stat_swap_enabled boolean not null default true;

update app.user_experience_profiles
   set tracked_stat_keys = coalesce(
     (
       select array_agg(distinct normalized_key)
       from (
         select lower(replace(replace(trim(item), '-', '_'), ' ', '_')) as normalized_key
           from unnest(coalesce(tracked_stat_keys, array[]::text[])) as item
          where trim(coalesce(item, '')) <> ''
         limit 5
       ) cleaned
       where normalized_key in (
         'resting_hr',
         'respiratory',
         'spo2',
         'hrv',
         'temperature',
         'steps',
         'heart_range',
         'blood_pressure'
       )
     ),
     array['resting_hr', 'respiratory', 'hrv', 'spo2', 'steps']::text[]
   ),
       smart_stat_swap_enabled = coalesce(smart_stat_swap_enabled, true);

commit;
