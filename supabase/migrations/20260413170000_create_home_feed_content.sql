begin;

create schema if not exists content;

create table if not exists content.home_feed_items (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  mode text not null default 'all'
    check (mode in ('all', 'scientific', 'mystical')),
  kind text not null default 'fact'
    check (kind in ('fact', 'tip', 'message')),
  title text not null,
  body text not null,
  link_label text null,
  link_url text null,
  active boolean not null default true,
  priority integer not null default 0,
  starts_at timestamptz null,
  ends_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (length(trim(title)) > 0),
  check (length(trim(body)) > 0)
);

create index if not exists home_feed_items_active_mode_idx
  on content.home_feed_items (active, mode, priority desc, created_at);

create index if not exists home_feed_items_schedule_idx
  on content.home_feed_items (starts_at, ends_at)
  where active = true;

alter table content.home_feed_items enable row level security;

drop policy if exists p_home_feed_items_select on content.home_feed_items;
create policy p_home_feed_items_select
on content.home_feed_items
for select
to authenticated
using (
  active = true
  and (starts_at is null or starts_at <= now())
  and (ends_at is null or ends_at >= now())
);

create table if not exists content.user_home_feed_seen (
  user_id uuid not null,
  item_id uuid not null references content.home_feed_items(id) on delete cascade,
  seen_at timestamptz not null default now(),
  dismissed_at timestamptz null,
  primary key (user_id, item_id)
);

create index if not exists user_home_feed_seen_user_seen_idx
  on content.user_home_feed_seen (user_id, seen_at desc);

alter table content.user_home_feed_seen enable row level security;

drop policy if exists p_user_home_feed_seen_select on content.user_home_feed_seen;
create policy p_user_home_feed_seen_select
on content.user_home_feed_seen
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_home_feed_seen_insert on content.user_home_feed_seen;
create policy p_user_home_feed_seen_insert
on content.user_home_feed_seen
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_home_feed_seen_update on content.user_home_feed_seen;
create policy p_user_home_feed_seen_update
on content.user_home_feed_seen
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

insert into content.home_feed_items (
  slug,
  mode,
  kind,
  title,
  body,
  priority
)
values
  (
    'science-aqi-small-particles',
    'scientific',
    'fact',
    'Air quality has layers',
    'AQI is a broad index. Fine particles, ozone, smoke, pollen, and weather can feel different even when the headline number looks similar.',
    20
  ),
  (
    'science-pressure-swing-baseline',
    'scientific',
    'tip',
    'Pressure swings are context, not a diagnosis',
    'Barometric shifts can line up with tension, sinus pressure, or fatigue for some people. Gaia Eyes treats that as context to compare with your own logs.',
    15
  ),
  (
    'science-sleep-pattern-protection',
    'scientific',
    'tip',
    'Sleep timing protects the read',
    'When sleep is short or shifted, Gaia Eyes uses that context so environmental patterns do not get too much credit for a rough body day.',
    10
  ),
  (
    'mystical-gaia-soft-baseline',
    'mystical',
    'message',
    'Keep your baseline soft',
    'The signal may be loud, but your job is not to match it. Let today be measured in steadiness, water, and one smaller load.',
    20
  ),
  (
    'mystical-moon-as-rhythm',
    'mystical',
    'message',
    'The moon is a rhythm marker',
    'Lunar windows are not commands. They are timing notes Gaia can compare with your sleep, recovery, and symptom history over time.',
    15
  ),
  (
    'mystical-weather-body-listening',
    'mystical',
    'message',
    'Your body reads weather too',
    'Pressure, humidity, and air clarity can move quietly in the background. Notice what changes, then let the data prove what repeats.',
    10
  ),
  (
    'all-context-flags-matter',
    'all',
    'tip',
    'Context flags matter',
    'Illness, allergen exposure, and heavy activity help Gaia Eyes avoid over-learning from days when something obvious is already affecting symptoms.',
    5
  )
on conflict (slug) do update
set mode = excluded.mode,
    kind = excluded.kind,
    title = excluded.title,
    body = excluded.body,
    priority = excluded.priority,
    active = true,
    updated_at = now();

commit;
