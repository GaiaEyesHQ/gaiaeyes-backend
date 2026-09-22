-- G046 revision of the G044 migration, confirmed UNAPPLIED by G045 metadata.
-- Apply this revised file AFTER G043; never run the frozen G044 file first.
-- This deliberately owner-checked, security-barrier view projects only rows
-- already classified public by the summary API (user_id IS NULL), never member
-- rows or arbitrary metrics_json. The preparer gets no underlying table grant.
-- Only two new role-scoped SELECT policies; existing policies/RLS stay intact.
-- No SECURITY DEFINER function, write grant, login or privileged role is added.
begin;
-- G045 observed the raw-column references through the view, not their types.
-- UTC bounds require an absolute timestamp: fail before any persistent change.
do $$ begin
  if not exists (
    select 1 from pg_attribute where attrelid='ext.schumann'::regclass
      and attname='ts_utc' and atttypid='timestamptz'::regtype and not attisdropped
  ) then
    raise exception 'EarthScope requires ext.schumann.ts_utc timestamp with time zone';
  end if;
end $$;
create view content.earthscope_writer_public_history with (security_barrier=true) as
select distinct on (day)
       day, updated_at, left(title, 160) as title, left(caption, 2048) as caption,
       left(metrics_json #>> '{social_variants,ig,caption}', 2048) as ig_caption,
       left(metrics_json #>> '{social_variants,fb,caption}', 2048) as fb_caption,
       metrics_json -> 'kp_max_24h' as kp_max_24h,
       metrics_json -> 'bz_min' as bz_min,
       metrics_json -> 'solar_wind_kms' as solar_wind_kms
from content.daily_posts
where user_id is null and platform='default'
order by day, updated_at desc, coalesce(caption,''), coalesce(title,'');
revoke all on content.earthscope_writer_public_history from public,anon,authenticated,service_role;
grant select on content.earthscope_writer_public_history to gaia_earthscope_writer_preparer;
grant usage on schema marts,ext to gaia_earthscope_writer_preparer;
grant select (sw_speed_now_kms,sw_speed_now,now_ts,kp_now)
    on marts.space_weather_daily to gaia_earthscope_writer_preparer;
grant select (kp_time,kp) on marts.kp_obs to gaia_earthscope_writer_preparer;
grant select (station_id,ts_utc,channel,value_num)
    on ext.schumann to gaia_earthscope_writer_preparer;
grant select (ts_utc,kp_index) on ext.space_weather to gaia_earthscope_writer_preparer;
grant select (ts,kp_latest) on ext.magnetosphere_pulse to gaia_earthscope_writer_preparer;
-- These are public environmental relations. Column grants bound the projection;
-- SELECT-only policies authorize rows for this role without adopting another role.
create policy earthscope_writer_preparer_kp on marts.kp_obs
    for select to gaia_earthscope_writer_preparer using (true);
create policy earthscope_writer_preparer_pulse on ext.magnetosphere_pulse
    for select to gaia_earthscope_writer_preparer using (true);
commit;
