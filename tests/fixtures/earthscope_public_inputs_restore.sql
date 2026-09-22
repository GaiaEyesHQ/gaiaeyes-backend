-- Prepared G046 grant restoration after exact target/source review.
-- Source relations/view and G043 roles must already exist. No login or secrets.
begin;
grant usage on schema marts,ext to gaia_earthscope_writer_preparer;
grant select on content.earthscope_writer_public_history to gaia_earthscope_writer_preparer;
grant select (sw_speed_now_kms,sw_speed_now,now_ts,kp_now)
  on marts.space_weather_daily to gaia_earthscope_writer_preparer;
grant select (kp_time,kp) on marts.kp_obs to gaia_earthscope_writer_preparer;
grant select (station_id,ts_utc,channel,value_num)
  on ext.schumann to gaia_earthscope_writer_preparer;
grant select (ts_utc,kp_index) on ext.space_weather to gaia_earthscope_writer_preparer;
grant select (ts,kp_latest) on ext.magnetosphere_pulse to gaia_earthscope_writer_preparer;
create policy earthscope_writer_preparer_kp on marts.kp_obs for select to gaia_earthscope_writer_preparer using (true);
create policy earthscope_writer_preparer_pulse on ext.magnetosphere_pulse for select to gaia_earthscope_writer_preparer using (true);
commit;
