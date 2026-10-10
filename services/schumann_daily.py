"""Latest station/day lookup without aggregating the entire raw history in UTC.

The indexed path matches the verified plain station/date AVG view over numeric
raw values, with the same raw-row visibility. The relkind guard does not verify
arbitrary future view definitions or RLS equivalence. Materialized/table
snapshots retain their original query, as do non-UTC sessions (including DST
midnight transitions) and nonfinite winning timestamps. The raw relation must
remain readable by the application role, including when SQL takes the fallback.
"""

LATEST_SCHUMANN_SQL = r"""
WITH fast_mode AS (
    SELECT current_setting('TimeZone') = 'UTC'
       AND (SELECT relkind = 'v' FROM pg_class
            WHERE oid = 'marts.schumann_daily'::regclass) AS enabled
), latest AS (
    SELECT s.station_id, s.priority, p.ts_utc::date AS day
    FROM (VALUES ('tomsk'::text, 0), ('cumiana'::text, 1)) AS s(station_id, priority)
    CROSS JOIN LATERAL (
        SELECT raw.ts_utc
        FROM ext.schumann AS raw
        WHERE raw.station_id = s.station_id
          AND raw.ts_utc < (%(day)s::date + 1)::timestamptz
        ORDER BY raw.ts_utc DESC
        LIMIT 1
    ) AS p
    WHERE (SELECT enabled FROM fast_mode)
), chosen AS (
    SELECT station_id, day
    FROM latest
    ORDER BY day DESC, priority
    LIMIT 1
), fast_result AS (
    SELECT c.station_id,
           avg(raw.value_num) FILTER (WHERE raw.channel = 'fundamental_hz') AS f0_avg_hz,
           avg(raw.value_num) FILTER (WHERE raw.channel = 'F1') AS f1_avg_hz,
           avg(raw.value_num) FILTER (WHERE raw.channel = 'F2') AS f2_avg_hz,
           avg(raw.value_num) FILTER (WHERE raw.channel = 'F3') AS f3_avg_hz,
           avg(raw.value_num) FILTER (WHERE raw.channel = 'F4') AS f4_avg_hz
    FROM chosen AS c
    JOIN ext.schumann AS raw
      ON raw.station_id = c.station_id
     AND raw.ts_utc >= c.day::timestamptz
     AND raw.ts_utc < (c.day + 1)::timestamptz
    WHERE isfinite(c.day)
    GROUP BY c.station_id
), fallback_result AS (
    SELECT station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz, f3_avg_hz, f4_avg_hz
    FROM marts.schumann_daily
    WHERE (
              NOT (SELECT enabled FROM fast_mode)
              OR EXISTS (SELECT 1 FROM chosen WHERE NOT isfinite(day))
          )
      AND station_id IN ('tomsk', 'cumiana')
      AND day <= %(day)s
    ORDER BY day DESC,
             CASE WHEN station_id = 'tomsk' THEN 0 WHEN station_id = 'cumiana' THEN 1 ELSE 2 END
    LIMIT 1
)
SELECT * FROM fast_result
UNION ALL
SELECT * FROM fallback_result;
"""
