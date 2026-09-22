-- Synthetic relevant hosted shape from G045; no copied application rows.
-- Run as postgres: NOSUPERUSER BYPASSRLS CREATEROLE CREATEDB, as observed.
create schema content; create schema marts; create schema ext; create schema raw;
grant usage on schema content,marts,ext to anon,authenticated,service_role;
alter default privileges in schema content grant select on tables to anon,authenticated;
alter default privileges in schema content grant select,insert,update,delete on tables to service_role;
alter default privileges in schema content grant select,usage on sequences to service_role;
alter default privileges in schema marts grant select on tables to anon,authenticated;
alter default privileges in schema marts grant select,insert,update,delete on tables to service_role;
alter default privileges in schema ext grant select on tables to anon,authenticated,service_role;
create table content.daily_posts(day date,updated_at timestamptz,title text,caption text,
  metrics_json jsonb,user_id uuid,platform text);
alter table content.daily_posts enable row level security;
create policy "anon read daily_posts" on content.daily_posts for select to anon using(true);
create table marts.space_weather_daily(day date primary key,updated_at timestamptz,kp_max numeric,
  bz_min numeric,sw_speed_avg numeric,flares_count integer,cmes_count integer,
  sw_speed_now_kms numeric,sw_speed_now numeric,now_ts timestamptz,kp_now numeric);
create table marts.kp_obs(kp_time timestamptz,kp numeric);
alter table marts.kp_obs enable row level security;
create policy "service_role full access kp_obs" on marts.kp_obs to service_role using(true) with check(true);
create table ext.space_weather(ts_utc timestamptz,kp_index numeric);
create table ext.magnetosphere_pulse(ts timestamptz,kp_latest double precision);
revoke all on ext.space_weather,ext.magnetosphere_pulse from anon,authenticated,service_role;
alter table ext.magnetosphere_pulse enable row level security;
create policy read_pulse_public on ext.magnetosphere_pulse for select to anon,authenticated using(true);
create policy ingest_pulse_service_role on ext.magnetosphere_pulse for insert to service_role with check(true);
-- These four raw columns/types are the contract to preflight; the hosted view
-- establishes their names/expressions but G045 did not inspect raw column types.
create table ext.schumann(station_id text,ts_utc timestamptz,channel text,value_num numeric);
create view marts.schumann_daily as
 SELECT station_id,
    date(ts_utc) AS day,
    avg(value_num) FILTER (WHERE channel = 'fundamental_hz'::text) AS f0_avg_hz,
    avg(value_num) FILTER (WHERE channel = 'F1'::text) AS f1_avg_hz,
    avg(value_num) FILTER (WHERE channel = 'F2'::text) AS f2_avg_hz,
    avg(value_num) FILTER (WHERE channel = 'F3'::text) AS f3_avg_hz,
    avg(value_num) FILTER (WHERE channel = 'F4'::text) AS f4_avg_hz,
    avg(value_num) FILTER (WHERE channel = 'F5'::text) AS f5_avg_hz
   FROM ext.schumann
  GROUP BY station_id, (date(ts_utc));;
-- A separate private canary is outside all allowed source grants.
create table raw.user_symptoms(secret text); insert into raw.user_symptoms values('PRIVATE CANARY');
insert into marts.space_weather_daily values ('2026-09-21','2026-09-21T01:00Z',6,-7,520,1,0,530,520,'2026-09-21T00:30Z',null);
insert into marts.kp_obs values ('2026-09-21T00:20Z',4);
insert into ext.magnetosphere_pulse values ('2026-09-21T00:15Z',3);
insert into ext.schumann values
 ('tomsk','2026-09-21T00:05Z','fundamental_hz',7.8),
 ('tomsk','2026-09-21T00:25Z','fundamental_hz',8.0),
 ('cumiana','2026-09-21T00:10Z','fundamental_hz',8.1),
 ('tomsk','2026-09-21T00:40Z','F1',14),
 ('tomsk','2026-09-20T23:59Z','fundamental_hz',99);
insert into content.daily_posts values
 ('2026-09-20','2026-09-20T21:00Z','Public title','Public caption','{"kp_max_24h":3,"private_canary":"PRIVATE JSON"}',null,'default'),
 ('2026-09-20','2026-09-20T22:00Z','PRIVATE MEMBER','PRIVATE ROW','{}','00000000-0000-0000-0000-000000000046','default'),
 ('2026-09-20','2026-09-20T23:00Z','PRIVATE PLATFORM','PRIVATE PLATFORM','{}',null,'member');
