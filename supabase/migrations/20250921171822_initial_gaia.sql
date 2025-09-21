

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "gaia";


ALTER SCHEMA "gaia" OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "gaia"."daily_summary" (
    "user_id" "uuid" NOT NULL,
    "date" "date" NOT NULL,
    "hr_min" numeric,
    "hr_max" numeric,
    "hrv_avg" numeric,
    "steps_total" numeric,
    "sleep_total_minutes" numeric,
    "spo2_avg" numeric,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sleep_rem_minutes" numeric,
    "sleep_core_minutes" numeric,
    "sleep_deep_minutes" numeric,
    "sleep_awake_minutes" numeric,
    "sleep_efficiency" numeric,
    "bp_sys_avg" double precision,
    "bp_dia_avg" double precision
);


ALTER TABLE "gaia"."daily_summary" OWNER TO "postgres";


CREATE OR REPLACE VIEW "gaia"."daily_summary_view" AS
 SELECT "user_id",
    "date",
    "hr_min",
    "hr_max",
    "hrv_avg",
    "steps_total",
    "sleep_total_minutes",
    "spo2_avg",
    "updated_at"
   FROM "gaia"."daily_summary";


ALTER VIEW "gaia"."daily_summary_view" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "gaia"."devices" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "platform" "text" NOT NULL,
    "source_name" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "devices_platform_check" CHECK (("platform" = ANY (ARRAY['ios'::"text", 'android'::"text"])))
);


ALTER TABLE "gaia"."devices" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "gaia"."samples" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "device_os" "text" NOT NULL,
    "source" "text",
    "type" "text" NOT NULL,
    "start_time" timestamp with time zone NOT NULL,
    "end_time" timestamp with time zone,
    "value_text" "text",
    "unit" "text",
    "metadata" "jsonb",
    "ingested_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "idempotency_hash" "text",
    "value" double precision,
    CONSTRAINT "samples_device_os_check" CHECK (("device_os" = ANY (ARRAY['ios'::"text", 'android'::"text"])))
);


ALTER TABLE "gaia"."samples" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "gaia"."sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "type" "text" NOT NULL,
    "start_time" timestamp with time zone NOT NULL,
    "end_time" timestamp with time zone,
    "summary_json" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "gaia"."sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "gaia"."users" (
    "id" "uuid" NOT NULL,
    "email" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "gaia"."users" OWNER TO "postgres";


ALTER TABLE ONLY "gaia"."daily_summary"
    ADD CONSTRAINT "daily_summary_pkey" PRIMARY KEY ("user_id", "date");



ALTER TABLE ONLY "gaia"."devices"
    ADD CONSTRAINT "devices_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "gaia"."samples"
    ADD CONSTRAINT "samples_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "gaia"."sessions"
    ADD CONSTRAINT "sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "gaia"."users"
    ADD CONSTRAINT "users_email_key" UNIQUE ("email");



ALTER TABLE ONLY "gaia"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_samples_idem_hash" ON "gaia"."samples" USING "btree" ("idempotency_hash");



CREATE INDEX "idx_samples_user_ts" ON "gaia"."samples" USING "btree" ("user_id", "start_time");



CREATE INDEX "idx_samples_user_type_time" ON "gaia"."samples" USING "btree" ("user_id", "type", "start_time");



CREATE UNIQUE INDEX "ux_samples_user_type_window" ON "gaia"."samples" USING "btree" ("user_id", "type", "start_time", "end_time");



ALTER TABLE ONLY "gaia"."daily_summary"
    ADD CONSTRAINT "daily_summary_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "gaia"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "gaia"."devices"
    ADD CONSTRAINT "devices_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "gaia"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "gaia"."samples"
    ADD CONSTRAINT "samples_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "gaia"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "gaia"."sessions"
    ADD CONSTRAINT "sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "gaia"."users"("id") ON DELETE CASCADE;



ALTER TABLE "gaia"."daily_summary" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "daily_summary_owner_select" ON "gaia"."daily_summary" FOR SELECT USING (("user_id" = "auth"."uid"()));



ALTER TABLE "gaia"."devices" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "devices_owner_delete" ON "gaia"."devices" FOR DELETE USING (("user_id" = "auth"."uid"()));



CREATE POLICY "devices_owner_insert" ON "gaia"."devices" FOR INSERT WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "devices_owner_select" ON "gaia"."devices" FOR SELECT USING (("user_id" = "auth"."uid"()));



CREATE POLICY "devices_owner_update" ON "gaia"."devices" FOR UPDATE USING (("user_id" = "auth"."uid"()));



ALTER TABLE "gaia"."samples" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "samples_owner_insert" ON "gaia"."samples" FOR INSERT WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "samples_owner_select" ON "gaia"."samples" FOR SELECT USING (("user_id" = "auth"."uid"()));



ALTER TABLE "gaia"."sessions" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "sessions_owner_insert" ON "gaia"."sessions" FOR INSERT WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "sessions_owner_select" ON "gaia"."sessions" FOR SELECT USING (("user_id" = "auth"."uid"()));



ALTER TABLE "gaia"."users" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "users_self_select" ON "gaia"."users" FOR SELECT USING (("id" = "auth"."uid"()));



CREATE POLICY "users_self_update" ON "gaia"."users" FOR UPDATE USING (("id" = "auth"."uid"()));



RESET ALL;
