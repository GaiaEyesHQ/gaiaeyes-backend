# Migraine time durable refresh migration

The apply filename is `supabase/migrations/20261110032646_add_migraine_time_refresh_queue.sql`, matching the production migration version assigned by Supabase on 2026-11-10 at 03:26:46 UTC. The registered name is `add_migraine_time_refresh_queue`.

This is a filename/reference reconciliation of the reviewed migration originally named `20261109210000_add_migraine_time_refresh_queue.sql`. SQL bytes are unchanged; SHA256 is `58ea64c460cc79203ebe6389add54dbea26bce9c40edfefb08e4412760089774`. It was applied once through the supported migration tool. Do not reapply it under the former filename or edit remote migration-history rows.

Keep `GAIA_MIGRAINE_TIME_EDITING_ENABLED=0` and `GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED=0` during rollout. Update all gauge, delta and pattern publishers, including both ingestion-worker instances, and drain old computations before enabling durable work. Verify worker failure/blocked-job monitoring and actual-ingress correction, readback and exact-retry behavior before public time editing is enabled.

The queue retains failed work and canonical receipts. Disable editing first for rollback; retain the additive tables and audits. Do not restore unfenced writers while durable jobs may run. Oversized work can require operator remediation rather than automatic completion.

## Worker flag ownership

The existing cron's `GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED` uses `sync: false` in `render-crons.yaml`. Render ignores this variable when updating an existing Blueprint, preserving its current runtime value. This prevents later syncs from undoing either activation or an emergency stop. See [Render's Blueprint reference](https://render.com/docs/blueprint-spec#prompting-for-secret-values).

During this configuration rollout, keep the existing runtime value at `0` and verify it remains `0` after Blueprint sync and deployment. This change does not enable the worker. Once all acceptance gates pass, set the existing cron's runtime value to `1` and verify a scheduled run; set it back to `0` to stop future drains. The application still defaults to disabled when the variable is absent or not exactly `1`. Do not change the Starter plan, five-minute schedule, or create another service.

For a newly created Blueprint, Render prompts for `sync: false` values; explicitly supply `0` until its own rollout gates pass. Existing resources are not prompted again. Public editing remains a separate runtime flag.
