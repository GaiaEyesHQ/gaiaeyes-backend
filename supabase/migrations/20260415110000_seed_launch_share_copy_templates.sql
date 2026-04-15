begin;

grant usage on schema content to authenticated, service_role;
grant select on table content.share_copy_templates to authenticated, service_role;

insert into content.share_copy_templates (
  slug,
  share_type,
  driver_key,
  surface,
  mode,
  tone,
  image_title,
  image_subtitle,
  caption,
  priority
)
values
  (
    'pattern-pollen-overall-balanced-v1',
    'personal_pattern',
    'pollen_overall_exposed',
    null,
    'all',
    'balanced',
    'Pollen days keep showing up',
    'Your logs are worth comparing',
    'Pollen exposure is showing up in your personal pattern history. Gaia Eyes compares seasonal irritants with symptoms like sinus pressure, headache, fatigue, and sensitivity so the repeat can be tested over time.',
    90
  ),
  (
    'daily-driver-stack-balanced-v1',
    'daily_state',
    'driver_stack',
    'all_drivers',
    'all',
    'balanced',
    'Influences are stacking',
    'Today has more than one active signal',
    'The live driver stack shows which earth, space, local, and body-context signals are active right now. Gaia Eyes turns the mix into a quick read on what may be shaping the day.',
    95
  )
on conflict (slug) do update
set share_type = excluded.share_type,
    driver_key = excluded.driver_key,
    surface = excluded.surface,
    mode = excluded.mode,
    tone = excluded.tone,
    image_title = excluded.image_title,
    image_subtitle = excluded.image_subtitle,
    caption = excluded.caption,
    priority = excluded.priority,
    active = true,
    updated_at = now();

commit;
