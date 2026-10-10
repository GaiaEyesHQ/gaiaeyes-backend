# Summary refresh: respiratory aggregate evaluation barrier

## Scope and evidence

This change adds only `MATERIALIZED` to `resp_rows` in
`gaia.refresh_daily_summary_user(uuid,date,text,integer)`. It does not change
sample predicates, timezone handling, the 45-day output window, the 225-day
source window, aggregates, upsert columns, or database settings persistently.

The reviewed production definition is the plain PL/pgSQL, volatile, non-strict,
security-invoker function owned by `postgres`, with no function configuration
(`proconfig`) and a null ACL (default privileges), cost 100 and parallel unsafe.
The defaults remain `America/Chicago` and 45; return type remains void.
`CREATE OR REPLACE` preserves the existing owner and ACL. The scripts additionally
compare the entire `pg_proc` row except `prosrc` before and after replacement,
so owner, privileges, security, search-path configuration, argument defaults and
other properties must all remain unchanged. No grants or owner changes are made.

Read-only production planning showed the respiratory aggregate under nested-loop
inner branches; low estimates can repeatedly evaluate its sleep-overlap work.
Historical statement statistics also showed substantial temporary-block traffic.
In a disposable PostgreSQL 17 reproduction with 53,000 synthetic samples and
5 MB work_mem, the original extracted SELECT exceeded 60 seconds; the single-CTE
barrier finished in 3.367 seconds. These are synthetic measurements, not a
production latency promise. Full stored-function parity and rollback tests are
in `tests/integration/test_summary_materialization.py`.

## Artifacts and guards

- Apply: `supabase/migrations/20261010171000_materialize_summary_resp_rows.sql`
- Exact rollback: `supabase/rollbacks/20261010171000_materialize_summary_resp_rows.sql`
- Original catalog definition MD5: `2d0f389e83fdb5bffcc520fe42006b55`
- Patched catalog definition MD5: `cedaa18418e89ba36fd14509b623e0fd`

The hashes are identification aids. The actual drift guard compares the complete
`pg_get_functiondef` text, not just a hash. Already-applied, missing, or differently
modified functions fail closed. Rollback accepts only the exact patched
function, so it cannot silently overwrite a later routine change. Both scripts are a single atomic DO statement, with no BEGIN/COMMIT that could
commit a migration runner's transaction early. They request a transaction-local
1-second lock timeout for subsequent DDL lock waits. This is not an overall
wall-clock deadline; the runner owns any outer execution timeout. The scripts
perform only single-function catalog work and replacement, never a refresh.
An error must stop the execution tool; do not continue individual statements.
The scripts do not call the refresh function or rewrite summary rows.

## Deployment order and approval boundary

Publishing or merging this PR does **not** authorize applying it to production.
The production stored-function replacement needs explicit approval identifying
this migration and the target Gaia Eyes database. Use the owning role; do not
change credentials, grants, or security settings to obtain access.

1. Complete PR review and CI. The checked repository workflows and startup
   configuration contain no production migration-apply step; Render application
   auto-deployment alone does not install this database change. Out-of-repository
   automation must be verified by the operator before merge/apply.
2. With approved read-only access, verify the exact function identity, original
   definition fingerprint and current owner/ACL/configuration. Stop on drift.
   Avoid concurrent routine DDL during the change window.
3. After explicit database-change approval, apply **only this migration** using
   the approved Supabase apply_migration tool that records migration history. Do not blindly
   push the repository's entire pending migration history. If the SQL is run
   directly, reconcile migration history using supported tooling before any
   later bulk migration operation; do not hand-edit migration history tables.
   The apply_migration tool does not expose an explicit version parameter: record
   the actual server-assigned version and reconcile any filename/version mismatch
   through supported tooling or a reviewed repository filename update.
4. Read back the patched fingerprint and unchanged function metadata. Allow
   already-authorized natural ingestion/retry work to run; no manual production
   refresh is required. Verify actual commits for previously failing keys,
   subsequent gauge completion, pool health and the next scheduled critical run.
5. If rollback is approved and needed, execute the exact guarded rollback script,
   verify the original fingerprint and unchanged metadata, and reconcile the
   recorded migration state through supported tooling. Rollback restores the
   old execution plan; it does not undo completed summary writes.

A drift-guard or lock-timeout failure is a stop-and-review result, not permission
to remove the guard, extend the timeout, or replace a different definition.

Reference: [PostgreSQL CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html)
documents replacement preserving owner/permissions while other properties are
set by the replacement definition; the catalog comparison is an additional
transactional safety check.
