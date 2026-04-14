begin;

create schema if not exists content;

create table if not exists content.share_copy_templates (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  share_type text not null
    check (share_type in ('signal_snapshot', 'personal_pattern', 'daily_state', 'event', 'outlook')),
  driver_key text null,
  surface text null,
  mode text not null default 'all'
    check (mode in ('all', 'scientific', 'mystical')),
  tone text not null default 'balanced'
    check (tone in ('straight', 'balanced', 'humorous')),
  image_title text null,
  image_subtitle text null,
  caption text not null,
  active boolean not null default true,
  priority integer not null default 0,
  starts_at timestamptz null,
  ends_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (length(trim(caption)) > 0),
  check (image_title is null or length(trim(image_title)) > 0),
  check (image_subtitle is null or length(trim(image_subtitle)) > 0),
  check (driver_key is null or length(trim(driver_key)) > 0),
  check (surface is null or length(trim(surface)) > 0)
);

create index if not exists share_copy_templates_match_idx
  on content.share_copy_templates (
    active,
    share_type,
    coalesce(driver_key, ''),
    coalesce(surface, ''),
    mode,
    tone,
    priority desc,
    updated_at desc
  );

create index if not exists share_copy_templates_schedule_idx
  on content.share_copy_templates (starts_at, ends_at)
  where active = true;

alter table content.share_copy_templates enable row level security;

drop policy if exists p_share_copy_templates_select on content.share_copy_templates;
create policy p_share_copy_templates_select
on content.share_copy_templates
for select
to authenticated
using (
  active = true
  and (starts_at is null or starts_at <= now())
  and (ends_at is null or ends_at >= now())
);

grant usage on schema content to authenticated, service_role;

grant select
on table content.share_copy_templates
to authenticated, service_role;

insert into content.share_copy_templates (
  slug,
  share_type,
  driver_key,
  mode,
  tone,
  image_title,
  image_subtitle,
  caption,
  priority
)
values
  (
    'signal-cme-balanced-v1',
    'signal_snapshot',
    'cme',
    'all',
    'balanced',
    'The Sun is throwing a tantrum',
    'Sleep may be affected',
    'The sun is throwing a tantrum. CMEs can stir geomagnetic conditions, and some people notice sleep, mood, or nervous-system shifts when the field gets louder. Sometimes what you feel is not random. Decode the unseen with Gaia Eyes.',
    100
  ),
  (
    'signal-solar-waves-balanced-v1',
    'signal_snapshot',
    'solar_waves',
    'all',
    'balanced',
    'Solar fire is turning up',
    'Your body may notice the field',
    'Solar activity is moving through the forecast. Some people notice sleep disruption, sensitivity, tension, or an off-rhythm feeling when space weather gets louder. Gaia Eyes helps compare the signal with your own body history.',
    95
  ),
  (
    'signal-flare-balanced-v1',
    'signal_snapshot',
    'flare',
    'all',
    'balanced',
    'Solar flare activity is awake',
    'Your system may feel the noise',
    'Solar flare activity can be part of a louder space-weather day. If you feel wired, sensitive, headachy, or off rhythm, Gaia Eyes helps keep the solar signal in context with your own logs.',
    95
  ),
  (
    'signal-schumann-balanced-v1',
    'signal_snapshot',
    'schumann',
    'all',
    'balanced',
    'Schumann spike',
    'Embrace the energy',
    'Schumann resonance is louder today. If you feel restless, buzzy, or unusually sensitive, take it as a cue to ground: breathe slowly, drink water, and get outside if you can. Gaia Eyes watches the signal without turning it into certainty.',
    100
  ),
  (
    'signal-solar-wind-balanced-v1',
    'signal_snapshot',
    'solar_wind',
    'all',
    'balanced',
    'The solar wind is shifting',
    'Your rhythm may notice',
    'Solar wind changes can nudge geomagnetic conditions and make some people feel wired, restless, or off rhythm. Gaia Eyes helps compare the space-weather signal with what your own body history shows.',
    95
  ),
  (
    'signal-kp-balanced-v1',
    'signal_snapshot',
    'kp',
    'all',
    'balanced',
    'The geomagnetic field is moving',
    'Sleep and sensitivity may shift',
    'Geomagnetic activity is part of today''s signal mix. Some people notice sleep, tension, focus, or nervous-system sensitivity when the field gets more active. Gaia Eyes turns that into context, not certainty.',
    95
  ),
  (
    'signal-pressure-balanced-v1',
    'signal_snapshot',
    'pressure',
    'all',
    'balanced',
    'Pressure is making a move',
    'Head, joints, and energy may notice',
    'Barometric pressure changes can be one of the loudest local signals for sensitive bodies. If your head, joints, or energy feel different today, Gaia Eyes can help compare the shift with your own history.',
    90
  ),
  (
    'signal-temp-balanced-v1',
    'signal_snapshot',
    'temp',
    'all',
    'balanced',
    'Temperature is changing the feel',
    'Your body may need more margin',
    'Temperature swings can add load even when the day looks ordinary. If energy, pain, or sensitivity feels different, Gaia Eyes helps keep local weather in the picture.',
    90
  ),
  (
    'signal-humidity-balanced-v1',
    'signal_snapshot',
    'humidity',
    'all',
    'balanced',
    'Humidity is not staying quiet',
    'Energy may feel heavier',
    'Humidity can change how much effort the same day takes. Some people notice heavier energy, more body load, or slower recovery when the air gets thick. Gaia Eyes watches that local layer beside your body signals.',
    90
  ),
  (
    'signal-aqi-balanced-v1',
    'signal_snapshot',
    'aqi',
    'all',
    'balanced',
    'The air is less forgiving today',
    'Sinus, head, and energy may notice',
    'Air quality is part of today''s signal mix. If your head, sinuses, breathing, or energy feel more sensitive, Gaia Eyes helps separate local air context from the rest of the environmental noise.',
    90
  ),
  (
    'signal-allergens-balanced-v1',
    'signal_snapshot',
    'allergens',
    'all',
    'balanced',
    'Seasonal irritants are louder',
    'Sinus and head pressure may notice',
    'Seasonal irritants can make symptoms look like a bigger environmental pattern than they really are. Gaia Eyes keeps allergen exposure in view so today''s read has better context.',
    90
  ),
  (
    'signal-current-symptoms-balanced-v1',
    'signal_snapshot',
    'current_symptoms',
    'all',
    'balanced',
    'Your body is part of the signal',
    'Today''s symptoms matter',
    'Symptoms are active in the read today. Gaia Eyes treats your body context as part of the picture, so environmental signals do not get all the credit for what you are feeling.',
    90
  ),
  (
    'signal-body-symptoms-balanced-v1',
    'signal_snapshot',
    'body_symptoms',
    'all',
    'balanced',
    'Your body is part of the signal',
    'Today''s symptoms matter',
    'Symptoms are active in the read today. Gaia Eyes treats your body context as part of the picture, so environmental signals do not get all the credit for what you are feeling.',
    90
  ),
  (
    'signal-temporary-illness-balanced-v1',
    'signal_snapshot',
    'temporary_illness',
    'all',
    'balanced',
    'Temporary illness changes the read',
    'Patterns should wait',
    'A temporary illness can turn symptoms up and make patterns harder to trust. Gaia Eyes can still show how today feels, while treating sick-day logs carefully so they do not create false long-term patterns.',
    90
  ),
  (
    'pattern-solar-wind-balanced-v1',
    'personal_pattern',
    'solar_wind_exposed',
    'all',
    'balanced',
    'This solar-wind link keeps repeating',
    'Your history is connecting the dots',
    'Solar wind is showing up in your personal pattern history. Gaia Eyes compares that repeat with your own symptom and body logs so the signal can stay useful without becoming a guarantee.',
    85
  ),
  (
    'pattern-bz-south-balanced-v1',
    'personal_pattern',
    'bz_south_exposed',
    'all',
    'balanced',
    'Southward Bz keeps showing up',
    'Your field days may have a pattern',
    'Southward Bz can help solar wind couple into Earth''s magnetic field. If this keeps overlapping your logs, Gaia Eyes treats it as a personal clue worth watching, not a verdict.',
    85
  ),
  (
    'pattern-kp-balanced-v1',
    'personal_pattern',
    'kp_g1_plus_exposed',
    'all',
    'balanced',
    'Geomagnetic days left breadcrumbs',
    'Your history noticed the repeat',
    'Kp-active days are showing up in your personal pattern history. Gaia Eyes helps compare those field changes with your sleep, symptoms, and recovery so you can see whether the repeat holds.',
    85
  ),
  (
    'pattern-humidity-balanced-v1',
    'personal_pattern',
    'humidity_extreme_exposed',
    'all',
    'balanced',
    'Humidity keeps showing up',
    'Your body history noticed',
    'Humidity extremes are showing up in your personal pattern history. Gaia Eyes compares those heavy-air days with your logs so you can spot whether energy, pain, or recovery tends to shift.',
    85
  ),
  (
    'pattern-aqi-balanced-v1',
    'personal_pattern',
    'aqi_moderate_plus_exposed',
    'all',
    'balanced',
    'The air-quality link keeps repeating',
    'Your logs are worth comparing',
    'Air quality is showing up in your personal pattern history. Gaia Eyes compares AQI with symptoms like sinus pressure, headache, fatigue, and focus so the repeat can be tested over time.',
    85
  ),
  (
    'pattern-pressure-balanced-v1',
    'personal_pattern',
    'pressure_swing_exposed',
    'all',
    'balanced',
    'Pressure swings keep leaving a trace',
    'Your history is worth watching',
    'Barometric pressure swings are showing up in your personal pattern history. Gaia Eyes compares those shifts with your symptoms and recovery so you can see whether the repeat keeps holding.',
    85
  ),
  (
    'pattern-schumann-balanced-v1',
    'personal_pattern',
    'schumann_exposed',
    'all',
    'balanced',
    'Earth resonance keeps showing up',
    'Your history noticed the pulse',
    'Schumann resonance is showing up in your personal pattern history. Gaia Eyes compares the resonance layer with your logs so you can watch the repeat without treating it as a certainty.',
    85
  ),
  (
    'pattern-temp-balanced-v1',
    'personal_pattern',
    'temp_swing_exposed',
    'all',
    'balanced',
    'Temperature swings left a trace',
    'Your history is worth comparing',
    'Temperature swings are showing up in your personal pattern history. Gaia Eyes compares those shifts with energy, pain, sleep, and sensitivity so the repeat can be tested over time.',
    85
  ),
  (
    'pattern-lunar-full-balanced-v1',
    'personal_pattern',
    'lunar_full_window_exposed',
    'all',
    'balanced',
    'The moon keeps showing up',
    'Your history is worth comparing',
    'A lunar window is showing up in your personal pattern history. Gaia Eyes does not treat the moon as a command, but it can compare timing with sleep, recovery, and symptoms when the repeats are there.',
    90
  ),
  (
    'pattern-lunar-new-balanced-v1',
    'personal_pattern',
    'lunar_new_window_exposed',
    'all',
    'balanced',
    'The moon keeps showing up',
    'Your history is worth comparing',
    'A lunar window is showing up in your personal pattern history. Gaia Eyes does not treat the moon as a command, but it can compare timing with sleep, recovery, and symptoms when the repeats are there.',
    90
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
