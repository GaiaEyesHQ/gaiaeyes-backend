# Supabase Schema Reference

This document summarizes the database objects created by the Supabase migrations in this repository. It is intended to provide a high-level reference for developers working with the Supabase instance.

## Schemas Overview

| Schema | Purpose |
| --- | --- |
| `gaia` | Core operational data captured from devices and daily summaries. |
| `dim` | Dimension / lookup tables supporting analytics, currently housing symptom metadata. |
| `raw` | Raw event store for user-captured symptom events. |
| `marts` | Analytics-optimized materialized views and derived datasets. |
| `ext` | External data sources referenced by marts (e.g., `ext.magnetosphere_pulse`). This schema is assumed to exist in the Supabase project but is not created by these migrations. |

> **Note:** The migrations also rely on Supabase's default `auth` schema for row-level security policies (e.g., `auth.uid()`).

## `gaia` Schema

### Tables

#### `gaia.daily_summary`
- **Composite Primary Key**: (`user_id`, `date`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `user_id` | `uuid` | Supabase Auth user identifier. |
  | `date` | `date` | Calendar date of the summary. |
  | `hr_min` | `numeric` | Minimum heart rate. |
  | `hr_max` | `numeric` | Maximum heart rate. |
  | `hrv_avg` | `numeric` | Average heart rate variability. |
  | `steps_total` | `numeric` | Total steps. |
  | `sleep_total_minutes` | `numeric` | Total sleep duration. |
  | `spo2_avg` | `numeric` | Average blood oxygen saturation. |
  | `updated_at` | `timestamptz` | Timestamp of last update (default `now()`). |
  | `sleep_rem_minutes` | `numeric` | REM sleep duration. |
  | `sleep_core_minutes` | `numeric` | Core sleep duration. |
  | `sleep_deep_minutes` | `numeric` | Deep sleep duration. |
  | `sleep_awake_minutes` | `numeric` | Awake duration. |
  | `sleep_efficiency` | `numeric` | Sleep efficiency score. |
  | `bp_sys_avg` | `double precision` | Average systolic blood pressure. |
  | `bp_dia_avg` | `double precision` | Average diastolic blood pressure. |

#### `gaia.devices`
- **Primary Key**: `id` (`uuid`, default `gen_random_uuid()`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `id` | `uuid` | Unique device identifier. |
  | `user_id` | `uuid` | Owner's Supabase Auth user ID. |
  | `platform` | `text` | Mobile platform (`ios` or `android`), enforced via check constraint. |
  | `source_name` | `text` | Optional display name or data source label. |
  | `created_at` | `timestamptz` | Creation timestamp (default `now()`). |

#### `gaia.samples`
- **Primary Key**: `id` (`uuid`, default `gen_random_uuid()`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `id` | `uuid` | Unique sample identifier. |
  | `user_id` | `uuid` | Owner's Supabase Auth user ID. |
  | `device_os` | `text` | Device operating system (`ios` or `android`). |
  | `source` | `text` | Data source identifier. |
  | `type` | `text` | Sample type (e.g., `heart_rate`). |
  | `start_time` | `timestamptz` | Sample start timestamp. |
  | `end_time` | `timestamptz` | Sample end timestamp (nullable). |
  | `value_text` | `text` | Textual value for categorical data. |
  | `unit` | `text` | Unit of measurement. |
  | `metadata` | `jsonb` | Arbitrary metadata payload. |
  | `ingested_at` | `timestamptz` | Ingestion timestamp (default `now()`). |
  | `idempotency_hash` | `text` | Optional idempotency key (indexed). |
  | `value` | `double precision` | Numeric measurement value. |
- **Indexes**
  - `idx_samples_idem_hash` on `idempotency_hash`
  - `idx_samples_user_ts` on (`user_id`, `start_time`)
  - `idx_samples_user_type_time` on (`user_id`, `type`, `start_time`)

#### `gaia.sessions`
- **Primary Key**: `id` (`uuid`, default `gen_random_uuid()`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `id` | `uuid` | Unique session identifier. |
  | `user_id` | `uuid` | Supabase Auth user ID. |
  | `type` | `text` | Session type (e.g., workout, meditation). |
  | `start_time` | `timestamptz` | Session start timestamp. |
  | `end_time` | `timestamptz` | Session end timestamp (nullable). |
  | `summary_json` | `jsonb` | Aggregated session metrics. |
  | `created_at` | `timestamptz` | Insertion timestamp (default `now()`). |

#### `gaia.users`
- **Primary Key**: `id` (`uuid`)
- **Unique Constraint**: `email`
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `id` | `uuid` | Supabase Auth user identifier. |
  | `email` | `text` | Unique email address (nullable). |
  | `created_at` | `timestamptz` | Creation timestamp (default `now()`). |

### Views

#### `gaia.daily_summary_view`
Projection of the `gaia.daily_summary` table limited to the core metrics:
- Columns: `user_id`, `date`, `hr_min`, `hr_max`, `hrv_avg`, `steps_total`, `sleep_total_minutes`, `spo2_avg`, `updated_at`

## `dim` Schema

### Tables

#### `dim.symptom_codes`
- **Primary Key**: `symptom_code` (`text`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `symptom_code` | `text` | Stable identifier for a symptom. |
  | `label` | `text` | User-facing label. |
  | `description` | `text` | Optional explanation of the symptom. |
  | `is_active` | `boolean` | Indicates if the symptom code is selectable (default `true`). |
- **Seed Data**: `nerve_pain`, `zaps`, `drained`, `headache`, `anxious`, `insomnia`, `other`

## `raw` Schema

### Tables

#### `raw.user_symptom_events`
- **Primary Key**: `id` (`uuid`, default `gen_random_uuid()`)
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `id` | `uuid` | Unique identifier for the logged event. |
  | `user_id` | `uuid` | Supabase Auth user ID (subject to row-level security). |
  | `ts_utc` | `timestamptz` | Event timestamp in UTC. |
  | `symptom_code` | `text` | Foreign key to `dim.symptom_codes(symptom_code)`. |
  | `severity` | `smallint` | Optional severity score (1–5) with constraint. |
  | `free_text` | `text` | User-entered notes. |
  | `tags` | `text[]` | Additional structured tags. |
  | `source` | `text` | Event source (default `'ios'`). |
  | `created_at` | `timestamptz` | Insertion timestamp (default `now()`). |
- **Indexes**
  - `user_symptom_events_user_ts_idx` on (`user_id`, `ts_utc` DESC)
  - `user_symptom_events_code_ts_idx` on (`symptom_code`, `ts_utc` DESC)
  - `user_symptom_events_tags_gin` on `tags` (GIN)
- **Row-Level Security**
  - `p_symptom_insert`: allows authenticated users to insert only for their own `user_id`.
  - `p_symptom_select`: allows authenticated users to read only their own events.
  - `p_symptom_delete`: allows authenticated users to delete only their own events.

## `marts` Schema

### Views

#### `marts.magnetosphere_last_24h`
- Standard view pulling the latest magnetosphere readings from `ext.magnetosphere_pulse` for the past 24 hours.
- Columns: `ts`, `r0_re`, `kp_latest`

### Materialized Views

#### `marts.symptom_daily`
Aggregated symptom metrics per day, user, and symptom code.
- **Base Query**: Aggregates `raw.user_symptom_events` grouped by `(day, user_id, symptom_code)`.
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `day` | `date` | Day of the events (`ts_utc` cast to date). |
  | `user_id` | `uuid` | Supabase Auth user ID. |
  | `symptom_code` | `text` | Symptom identifier. |
  | `events` | `bigint` | Number of events logged that day. |
  | `mean_severity` | `double precision` | Average severity across events. |
  | `last_ts` | `timestamptz` | Timestamp of the most recent event that day. |
- **Unique Index**: `symptom_daily_pk` on (`day`, `user_id`, `symptom_code`)

#### `marts.symptom_x_space_daily`
Joins daily symptom aggregates with space weather datasets.
- **Data Sources**
  - `marts.symptom_daily`
  - `marts.daily_features` *(must exist separately)*
  - `marts.schumann_daily` *(must exist separately)*
- **Columns**
  | Column | Type | Description |
  | --- | --- | --- |
  | `day` | `date` | Calendar day. |
  | `user_id` | `uuid` | Supabase Auth user ID. |
  | `symptom_events` | `bigint` | Sum of events from `symptom_daily`. |
  | `mean_severity` | `double precision` | Average severity across the day. |
  | `kp_max` | `numeric` | Maximum Kp index (from `marts.daily_features`). |
  | `bz_min` | `numeric` | Minimum Bz magnetic component (from `marts.daily_features`). |
  | `sw_speed_avg` | `numeric` | Average solar wind speed (from `marts.daily_features`). |
  | `sch_f0_avg` | `numeric` | Average Schumann resonance frequency (from `marts.schumann_daily`). |
- **Unique Index**: `symptom_x_space_daily_pk` on (`day`, `user_id`)

### Functions

#### `marts.refresh_symptom_marts()`
Refresh helper for analytics materialized views.
- **Signature**: `marts.refresh_symptom_marts() RETURNS void`
- **Behavior**: Runs `REFRESH MATERIALIZED VIEW CONCURRENTLY` on both `marts.symptom_daily` and `marts.symptom_x_space_daily`.

### Maintenance

- The migration script refreshes both materialized views immediately after creation using `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
- Future jobs can call `marts.refresh_symptom_marts()` to keep marts synchronized.

## Seed & Utility Routines

### Nerve Pain Symptom Code Upsert
Migration `20251017123000_seed_nerve_pain_symptom_code.sql` ensures a `nerve_pain` symptom code exists in any schema containing a `symptom_codes` table, gracefully handling column variations.

## External Dependencies

- `gen_random_uuid()` from the `pgcrypto` extension is required for UUID defaults.
- `auth.uid()` (Supabase) is used in row-level security policies.
- `ext.magnetosphere_pulse`, `marts.daily_features`, and `marts.schumann_daily` must exist for dependent views/materialized views to function.

## Context-Only Schemas

The Supabase instance also exposes several supporting schemas that are not created by the migrations in this repository but are
referred to by downstream analytics. The following DDL snippets are provided **for reference only** and should not be executed as-is.

### `content` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE content.asset (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  storage_path text NOT NULL,
  mime text,
  width integer,
  height integer,
  alt_text text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  meta jsonb,
  CONSTRAINT asset_pkey PRIMARY KEY (id)
);
CREATE TABLE content.daily_posts (
  id bigint NOT NULL DEFAULT nextval('content.daily_posts_id_seq'::regclass),
  day date NOT NULL,
  user_id uuid,
  platform text NOT NULL DEFAULT 'default'::text,
  title text,
  caption text,
  body_markdown text,
  hashtags text,
  metrics_json jsonb,
  sources_json jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT daily_posts_pkey PRIMARY KEY (id)
);
CREATE TABLE content.item (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind = ANY (ARRAY['post'::text, 'article'::text, 'story'::text, 'image'::text, 'video'::text, 'thread'::text])),
  slug text UNIQUE,
  title text,
  summary text,
  body jsonb,
  status text NOT NULL DEFAULT 'draft'::text CHECK (status = ANY (ARRAY['draft'::text, 'scheduled'::text, 'published'::text, 'archived'::text])),
  author text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  published_at timestamp with time zone,
  sources_json jsonb,
  CONSTRAINT item_pkey PRIMARY KEY (id)
);
CREATE TABLE content.item_asset (
  item_id uuid NOT NULL,
  asset_id uuid NOT NULL,
  role text NOT NULL DEFAULT 'inline'::text CHECK (role = ANY (ARRAY['cover'::text, 'inline'::text, 'gallery'::text, 'thumb'::text])),
  position integer,
  CONSTRAINT item_asset_pkey PRIMARY KEY (item_id, asset_id, role),
  CONSTRAINT item_asset_item_id_fkey FOREIGN KEY (item_id) REFERENCES content.item(id),
  CONSTRAINT item_asset_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES content.asset(id)
);
CREATE TABLE content.item_tag (
  item_id uuid NOT NULL,
  tag_id bigint NOT NULL,
  CONSTRAINT item_tag_pkey PRIMARY KEY (item_id, tag_id),
  CONSTRAINT item_tag_item_id_fkey FOREIGN KEY (item_id) REFERENCES content.item(id),
  CONSTRAINT item_tag_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES content.tag(id)
);
CREATE TABLE content.schedule (
  item_id uuid NOT NULL,
  run_at timestamp with time zone NOT NULL,
  platform text NOT NULL,
  status text DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'sent'::text, 'skipped'::text, 'failed'::text])),
  result_json jsonb,
  CONSTRAINT schedule_pkey PRIMARY KEY (item_id, run_at, platform),
  CONSTRAINT schedule_item_id_fkey FOREIGN KEY (item_id) REFERENCES content.item(id)
);
CREATE TABLE content.tag (
  id bigint NOT NULL DEFAULT nextval('content.tag_id_seq'::regclass),
  slug text UNIQUE,
  name text,
  CONSTRAINT tag_pkey PRIMARY KEY (id)
);
```

### `cron` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE cron.job (
  jobid bigint NOT NULL DEFAULT nextval('cron.jobid_seq'::regclass),
  schedule text NOT NULL,
  command text NOT NULL,
  nodename text NOT NULL DEFAULT 'localhost'::text,
  nodeport integer NOT NULL DEFAULT inet_server_port(),
  database text NOT NULL DEFAULT current_database(),
  username text NOT NULL DEFAULT CURRENT_USER,
  active boolean NOT NULL DEFAULT true,
  jobname text,
  CONSTRAINT job_pkey PRIMARY KEY (jobid)
);
CREATE TABLE cron.job_run_details (
  jobid bigint,
  runid bigint NOT NULL DEFAULT nextval('cron.runid_seq'::regclass),
  job_pid integer,
  database text,
  username text,
  command text,
  status text,
  return_message text,
  start_time timestamp with time zone,
  end_time timestamp with time zone,
  CONSTRAINT job_run_details_pkey PRIMARY KEY (runid)
);
```

### `ext` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE ext.donki_event (
  event_id text NOT NULL,
  event_type text NOT NULL,
  start_time timestamp with time zone,
  peak_time timestamp with time zone,
  end_time timestamp with time zone,
  class text,
  source text DEFAULT 'nasa-donki'::text,
  meta jsonb,
  ingested_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT donki_event_pkey PRIMARY KEY (event_id)
);
CREATE TABLE ext.earthquakes (
  event_id text NOT NULL,
  origin_time timestamp with time zone NOT NULL,
  mag numeric,
  depth_km numeric,
  lat numeric,
  lon numeric,
  place text,
  src text DEFAULT 'usgs'::text,
  meta jsonb,
  ingested_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT earthquakes_pkey PRIMARY KEY (event_id)
);
CREATE TABLE ext.earthquakes_day (
  day date NOT NULL,
  total_all integer,
  buckets_day jsonb,
  fetched_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT earthquakes_day_pkey PRIMARY KEY (day)
);
CREATE TABLE ext.earthquakes_events (
  usgs_id text NOT NULL,
  time_utc timestamp with time zone NOT NULL,
  mag numeric,
  mag_type text,
  depth_km numeric,
  place text,
  latitude numeric,
  longitude numeric,
  url text,
  source text DEFAULT 'usgs'::text,
  inserted_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT earthquakes_events_pkey PRIMARY KEY (usgs_id)
);
CREATE TABLE ext.local_weather (
  location_id text NOT NULL,
  ts_utc timestamp with time zone NOT NULL,
  temp_c numeric,
  humidity_pct numeric,
  pressure_hpa numeric,
  wind_mps numeric,
  precip_mm numeric,
  meta jsonb,
  CONSTRAINT local_weather_pkey PRIMARY KEY (location_id, ts_utc)
);
CREATE TABLE ext.magnetosphere_pulse (
  ts timestamp with time zone NOT NULL,
  n_cm3 double precision,
  v_kms double precision,
  bz_nt double precision,
  pdyn_npa double precision,
  r0_re double precision,
  symh_est integer,
  dbdt_proxy double precision,
  trend_r0 text,
  geo_risk text,
  kpi_bucket text,
  lpp_re double precision,
  kp_latest double precision,
  CONSTRAINT magnetosphere_pulse_pkey PRIMARY KEY (ts)
);
CREATE TABLE ext.schumann (
  station_id text NOT NULL,
  ts_utc timestamp with time zone NOT NULL,
  channel text NOT NULL,
  value_num numeric,
  unit text,
  meta jsonb,
  CONSTRAINT schumann_pkey PRIMARY KEY (station_id, ts_utc, channel),
  CONSTRAINT schumann_station_id_fkey FOREIGN KEY (station_id) REFERENCES ext.schumann_station(station_id)
);
CREATE TABLE ext.schumann_station (
  station_id text NOT NULL,
  name text,
  lat numeric,
  lon numeric,
  meta jsonb,
  CONSTRAINT schumann_station_pkey PRIMARY KEY (station_id)
);
CREATE TABLE ext.space_alerts (
  issued_at timestamp with time zone NOT NULL,
  src text NOT NULL,
  message text NOT NULL,
  meta jsonb,
  CONSTRAINT space_alerts_pkey PRIMARY KEY (issued_at, src, message)
);
CREATE TABLE ext.space_forecast (
  fetched_at timestamp with time zone NOT NULL,
  src text NOT NULL,
  body_text text NOT NULL,
  CONSTRAINT space_forecast_pkey PRIMARY KEY (fetched_at, src)
);
CREATE TABLE ext.space_news_raw (
  id bigint NOT NULL DEFAULT nextval('ext.space_news_raw_id_seq'::regclass),
  source text,
  link text UNIQUE,
  title text,
  published_at timestamp with time zone,
  raw jsonb,
  inserted_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT space_news_raw_pkey PRIMARY KEY (id)
);
CREATE TABLE ext.space_visuals (
  id bigint NOT NULL DEFAULT nextval('ext.space_visuals_id_seq'::regclass),
  ts timestamp with time zone NOT NULL,
  key text NOT NULL,
  image_path text,
  meta jsonb,
  CONSTRAINT space_visuals_pkey PRIMARY KEY (id)
);
CREATE TABLE ext.space_weather (
  ts_utc timestamp with time zone NOT NULL,
  kp_index numeric,
  bz_nt numeric,
  sw_speed_kms numeric,
  src text DEFAULT 'noaa'::text,
  meta jsonb,
  CONSTRAINT space_weather_pkey PRIMARY KEY (ts_utc)
);
```

### `marts` Schema (Additional Tables)

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE marts.daily_features (
  user_id uuid NOT NULL,
  day date NOT NULL,
  hr_min numeric,
  hr_max numeric,
  hrv_avg numeric,
  steps_total numeric,
  sleep_total_minutes numeric,
  sleep_rem_minutes numeric,
  sleep_core_minutes numeric,
  sleep_deep_minutes numeric,
  sleep_awake_minutes numeric,
  sleep_efficiency numeric,
  spo2_avg numeric,
  bp_sys_avg numeric,
  bp_dia_avg numeric,
  kp_max numeric,
  bz_min numeric,
  sw_speed_avg numeric,
  src text DEFAULT 'rollup-v1'::text,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  flares_count integer,
  cmes_count integer,
  schumann_station text,
  sch_fundamental_avg_hz numeric,
  sch_f1_avg_hz numeric,
  sch_f2_avg_hz numeric,
  sch_f3_avg_hz numeric,
  sch_f4_avg_hz numeric,
  sch_f5_avg_hz numeric,
  sch_cumiana_station text,
  sch_cumiana_fundamental_avg_hz numeric,
  sch_cumiana_f1_avg_hz numeric,
  sch_cumiana_f2_avg_hz numeric,
  sch_cumiana_f3_avg_hz numeric,
  sch_cumiana_f4_avg_hz numeric,
  sch_cumiana_f5_avg_hz numeric,
  sch_any_fundamental_avg_hz numeric,
  sch_any_f1_avg_hz numeric,
  sch_any_f2_avg_hz numeric,
  sch_any_f3_avg_hz numeric,
  sch_any_f4_avg_hz numeric,
  sch_any_f5_avg_hz numeric,
  CONSTRAINT daily_features_pkey PRIMARY KEY (user_id, day)
);
CREATE TABLE marts.magnetosphere_daily (
  day date NOT NULL,
  r0_min double precision,
  r0_max double precision,
  symh_min integer,
  geo_risk_hours integer,
  notes text,
  CONSTRAINT magnetosphere_daily_pkey PRIMARY KEY (day)
);
CREATE TABLE marts.quakes_daily (
  day date NOT NULL,
  all_quakes integer,
  m4p integer,
  m5p integer,
  m6p integer,
  m7p integer,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT quakes_daily_pkey PRIMARY KEY (day)
);
CREATE TABLE marts.quakes_history_expanded (
  month date NOT NULL,
  total_quakes integer,
  m4p integer,
  m5p integer,
  m6p integer,
  m7p integer,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT quakes_history_expanded_pkey PRIMARY KEY (month)
);
CREATE TABLE marts.quakes_monthly (
  month date NOT NULL,
  all_quakes integer,
  m4p integer,
  m5p integer,
  m6p integer,
  m7p integer,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT quakes_monthly_pkey PRIMARY KEY (month)
);
CREATE TABLE marts.space_news (
  id bigint NOT NULL DEFAULT nextval('marts.space_news_id_seq'::regclass),
  title text,
  summary text,
  category text,
  tags text[],
  published_at timestamp with time zone,
  source_url text UNIQUE,
  tone text,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT space_news_pkey PRIMARY KEY (id)
);
CREATE TABLE marts.space_weather_daily (
  day date NOT NULL,
  kp_max numeric,
  bz_min numeric,
  sw_speed_avg numeric,
  row_count integer,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  flares_count integer,
  cmes_count integer,
  CONSTRAINT space_weather_daily_pkey PRIMARY KEY (day)
);
```

### `net` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE net._http_response (
  id bigint,
  status_code integer,
  content_type text,
  headers jsonb,
  content text,
  timed_out boolean,
  error_msg text,
  created timestamp with time zone NOT NULL DEFAULT now()
);
CREATE TABLE net.http_request_queue (
  id bigint NOT NULL DEFAULT nextval('net.http_request_queue_id_seq'::regclass),
  method text NOT NULL,
  url text NOT NULL,
  headers jsonb NOT NULL,
  body bytea,
  timeout_milliseconds integer NOT NULL
);
```

### `realtime` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE realtime.messages (
  topic text NOT NULL,
  extension text NOT NULL,
  payload jsonb,
  event text,
  private boolean DEFAULT false,
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  inserted_at timestamp without time zone NOT NULL DEFAULT now(),
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  CONSTRAINT messages_pkey PRIMARY KEY (id, inserted_at)
);
CREATE TABLE realtime.schema_migrations (
  version bigint NOT NULL,
  inserted_at timestamp without time zone,
  CONSTRAINT schema_migrations_pkey PRIMARY KEY (version)
);
CREATE TABLE realtime.subscription (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  subscription_id uuid NOT NULL,
  entity regclass NOT NULL,
  filters realtime.user_defined_filter[] NOT NULL DEFAULT '{}'::realtime.user_defined_filter[],
  claims jsonb NOT NULL,
  claims_role regrole NOT NULL DEFAULT realtime.to_regrole((claims ->> 'role'::text)),
  created_at timestamp without time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT subscription_pkey PRIMARY KEY (id)
);
```

### `storage` Schema

```sql
-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE storage.buckets (
  id text NOT NULL,
  name text NOT NULL,
  owner uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  public boolean DEFAULT false,
  avif_autodetection boolean DEFAULT false,
  file_size_limit bigint,
  allowed_mime_types text[],
  owner_id text,
  type storage.buckettype NOT NULL DEFAULT 'STANDARD'::storage.buckettype,
  CONSTRAINT buckets_pkey PRIMARY KEY (id)
);
CREATE TABLE storage.buckets_analytics (
  id text NOT NULL,
  type storage.buckettype NOT NULL DEFAULT 'ANALYTICS'::storage.buckettype,
  format text NOT NULL DEFAULT 'ICEBERG'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT buckets_analytics_pkey PRIMARY KEY (id)
);
CREATE TABLE storage.migrations (
  id integer NOT NULL,
  name character varying NOT NULL UNIQUE,
  hash character varying NOT NULL,
  executed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT migrations_pkey PRIMARY KEY (id)
);
CREATE TABLE storage.objects (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  bucket_id text,
  name text,
  owner uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  last_accessed_at timestamp with time zone DEFAULT now(),
  metadata jsonb,
  path_tokens text[] DEFAULT string_to_array(name, '/'::text),
  version text,
  owner_id text,
  user_metadata jsonb,
  level integer,
  CONSTRAINT objects_pkey PRIMARY KEY (id),
  CONSTRAINT objects_bucketId_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id)
);
CREATE TABLE storage.prefixes (
  bucket_id text NOT NULL,
  name text NOT NULL,
  level integer NOT NULL DEFAULT storage.get_level(name),
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT prefixes_pkey PRIMARY KEY (bucket_id, level, name),
  CONSTRAINT prefixes_bucketId_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id)
);
CREATE TABLE storage.s3_multipart_uploads (
  id text NOT NULL,
  in_progress_size bigint NOT NULL DEFAULT 0,
  upload_signature text NOT NULL,
  bucket_id text NOT NULL,
  key text NOT NULL,
  version text NOT NULL,
  owner_id text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  user_metadata jsonb,
  CONSTRAINT s3_multipart_uploads_pkey PRIMARY KEY (id),
  CONSTRAINT s3_multipart_uploads_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id)
);
CREATE TABLE storage.s3_multipart_uploads_parts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  upload_id text NOT NULL,
  size bigint NOT NULL DEFAULT 0,
  part_number integer NOT NULL,
  bucket_id text NOT NULL,
  key text NOT NULL,
  etag text NOT NULL,
  owner_id text,
  version text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT s3_multipart_uploads_parts_pkey PRIMARY KEY (id),
  CONSTRAINT s3_multipart_uploads_parts_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES storage.s3_multipart_uploads(id),
  CONSTRAINT s3_multipart_uploads_parts_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES storage.buckets(id)
);
```

## Change History

| Migration | Summary |
| --- | --- |
| `20250921171822_initial_gaia.sql` | Initial core schemas (`gaia` tables and indexes). |
| `20251015142333_create_marts_magnetosphere_last24_view.sql` | Adds `marts.magnetosphere_last_24h` view. |
| `20251017123000_seed_nerve_pain_symptom_code.sql` | Seeds/updates `nerve_pain` symptom code across available schemas. |
| `20251019140000_setup_symptom_domain.sql` | Establishes symptom domain tables, RLS, materialized views, and helper function. |

---

For questions or future schema changes, update this document alongside new Supabase migrations to keep the reference accurate.
