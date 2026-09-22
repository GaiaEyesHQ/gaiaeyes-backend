-- G046 explicit SET ROLE membership; no implicit inheritance into app logins.
-- PREPARED ONLY. Use only after identifying the actual target login roles,
-- preserving catalog/privilege before evidence and applying the queue migration.
-- No credentials are created. psql variables are quoted identifiers, not SQL text.
\set ON_ERROR_STOP on
\if :{?api_login_role}
\else
  \echo 'Missing verified api_login_role'
  \quit 3
\endif
\if :{?preparer_login_role}
\else
  \echo 'Missing verified preparer_login_role'
  \quit 3
\endif
begin;
grant gaia_earthscope_writer_backend to :"api_login_role" with inherit false, set true;
grant gaia_earthscope_writer_preparer to :"preparer_login_role" with inherit false, set true;
grant usage on schema marts to gaia_earthscope_writer_preparer;
grant select (day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count)
  on marts.space_weather_daily to gaia_earthscope_writer_preparer;
commit;
