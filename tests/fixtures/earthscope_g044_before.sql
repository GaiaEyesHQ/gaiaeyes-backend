-- Additive, default-off G044 preparation. Apply AFTER the G043 queue migration.
-- This deliberately owner-checked, security-barrier view projects only rows
-- already classified public by the summary API (user_id IS NULL), never member
-- rows or arbitrary metrics_json. The preparer gets no underlying table grant.
-- No SECURITY DEFINER function, policy change, write grant or login is added.
begin;
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
grant select (station_id,day,f0_avg_hz,last_fundamental_ts)
    on marts.schumann_daily to gaia_earthscope_writer_preparer;
grant select (ts_utc,kp_index) on ext.space_weather to gaia_earthscope_writer_preparer;
grant select (ts,kp_latest) on ext.magnetosphere_pulse to gaia_earthscope_writer_preparer;
commit;
