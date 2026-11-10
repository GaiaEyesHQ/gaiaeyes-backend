# Migraine time durable refresh migration

The apply filename is `supabase/migrations/20261110032646_add_migraine_time_refresh_queue.sql`, matching the production migration version assigned by Supabase on 2026-11-10 at 03:26:46 UTC. The registered name is `add_migraine_time_refresh_queue`.

This is a filename/reference reconciliation of the reviewed migration originally named `20261109210000_add_migraine_time_refresh_queue.sql`. SQL bytes are unchanged; SHA256 is `58ea64c460cc79203ebe6389add54dbea26bce9c40edfefb08e4412760089774`. It was applied once through the supported migration tool. Do not reapply it under the former filename or edit remote migration-history rows.

Keep `GAIA_MIGRAINE_TIME_EDITING_ENABLED=0` and `GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED=0` during rollout. Update all gauge, delta and pattern publishers, including both ingestion-worker instances, and drain old computations before enabling durable work. Verify worker failure/blocked-job monitoring and actual-ingress correction, readback and exact-retry behavior before public time editing is enabled.

The queue retains failed work and canonical receipts. Disable editing first for rollback; retain the additive tables and audits. Do not restore unfenced writers while durable jobs may run. Oversized work can require operator remediation rather than automatic completion.
