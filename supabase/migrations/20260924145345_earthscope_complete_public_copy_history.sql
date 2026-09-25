-- G053: bounded prior complete-copy context, public/default rows only.
-- Append named text projections; never expose arbitrary metrics or grant the base table.
-- Apply after revised G046; existing transport contract is unchanged.
begin;
create or replace view content.earthscope_writer_public_history with (security_barrier=true) as
select distinct on (day)
       day, updated_at, left(title, 160) as title, left(caption, 2048) as caption,
       left(metrics_json #>> '{social_variants,ig,caption}', 2048) as ig_caption,
       left(metrics_json #>> '{social_variants,fb,caption}', 2048) as fb_caption,
       metrics_json -> 'kp_max_24h' as kp_max_24h,
       metrics_json -> 'bz_min' as bz_min,
       metrics_json -> 'solar_wind_kms' as solar_wind_kms,
       left(metrics_json #>> '{sections,snapshot}', 768) as snapshot,
       left(metrics_json #>> '{sections,affects}', 768) as affects,
       left(metrics_json #>> '{sections,playbook}', 768) as playbook,
       left(metrics_json #>> '{sections,voiceover}', 768) as voiceover,
       left(metrics_json #>> '{sections,reel_story,hook}', 256) as reel_hook,
       left(metrics_json #>> '{sections,reel_story,signal}', 256) as reel_signal,
       left(metrics_json #>> '{sections,reel_story,effects}', 256) as reel_effects,
       left(metrics_json #>> '{sections,reel_story,pattern}', 256) as reel_pattern,
       left(metrics_json #>> '{sections,reel_story,voiceover}', 256) as reel_voiceover
from content.daily_posts
where user_id is null and platform='default'
order by day, updated_at desc, coalesce(caption,''), coalesce(title,'');
revoke all on content.earthscope_writer_public_history from public,anon,authenticated,service_role;
grant select on content.earthscope_writer_public_history to gaia_earthscope_writer_preparer;
-- Trusted cloud publisher only. No member data or worker/preparer access.
create table content.earthscope_delivery_attempts (
    day date not null,
    channel text not null check (channel in ('ig_carousel','fb_carousel','ig_reel','fb_reel')),
    post_sha256 text not null check (post_sha256 ~ '^[0-9a-f]{64}$'),
    destination_sha256 text not null check (destination_sha256 ~ '^[0-9a-f]{64}$'),
    media_revision text not null check (media_revision ~ '^[0-9a-f]{64}$'),
    attempt_id uuid not null unique,
    state text not null check (state in ('reserved','published','uncertain')),
    post_id text,
    created_at timestamptz not null default now(),
    primary key (day,channel),
    check (state <> 'published' or post_id is not null)
);
alter table content.earthscope_delivery_attempts enable row level security;
revoke all on content.earthscope_delivery_attempts from public,anon,authenticated,service_role;
grant select,insert on content.earthscope_delivery_attempts to service_role;
grant update (state,post_id) on content.earthscope_delivery_attempts to service_role;
commit;
