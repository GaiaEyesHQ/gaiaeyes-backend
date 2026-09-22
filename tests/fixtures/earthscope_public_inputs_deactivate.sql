-- Prepared G046 permission rollback only; no rows/views/tables are removed.
-- First disable draft producer/API and preserve receipts. Review catalog drift.
-- Does not undo the original G043 daily-mart or queue grants.
begin;
revoke select on content.earthscope_writer_public_history from gaia_earthscope_writer_preparer;
revoke select (sw_speed_now_kms,sw_speed_now,now_ts,kp_now)
  on marts.space_weather_daily from gaia_earthscope_writer_preparer;
revoke select (kp_time,kp) on marts.kp_obs from gaia_earthscope_writer_preparer;
revoke select (station_id,ts_utc,channel,value_num)
  on ext.schumann from gaia_earthscope_writer_preparer;
revoke select (ts_utc,kp_index) on ext.space_weather from gaia_earthscope_writer_preparer;
revoke select (ts,kp_latest) on ext.magnetosphere_pulse from gaia_earthscope_writer_preparer;
drop policy earthscope_writer_preparer_kp on marts.kp_obs;
drop policy earthscope_writer_preparer_pulse on ext.magnetosphere_pulse;
commit;
