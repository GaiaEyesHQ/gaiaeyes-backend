begin;

alter table if exists app.user_experience_profiles
  add column if not exists favorite_symptom_codes text[] not null default array[]::text[];

update app.user_experience_profiles
   set favorite_symptom_codes = coalesce(
         (
           select array(
             select distinct upper(replace(replace(trim(item), '-', '_'), ' ', '_'))
               from unnest(coalesce(favorite_symptom_codes, array[]::text[])) as item
              where trim(coalesce(item, '')) <> ''
              limit 6
           )
         ),
         array[]::text[]
       );

commit;
