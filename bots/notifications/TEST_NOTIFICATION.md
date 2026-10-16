# Single-registration APNs diagnostic

`send_test_notification.py` is an explicit operator command, separate from the normal sender and scheduler. It sends fixed generic text to one iOS registration. It does not consume queued events or change registrations, preferences, delivery records, or any other database data.

Use only an already authorized execution environment with its existing database and APNs configuration. Do not copy credentials or device tokens into commands, output, tickets, or tools. This command resolves the device token internally only when an explicit send is requested and all metadata checks pass.

Preflight example (placeholders are intentional):

```sh
python -m bots.notifications.send_test_notification \
  --registration-id '<exact registration UUID>' \
  --user-id '<exact account UUID>' \
  --expected-app-version '1.0.1 (9)' \
  --expected-environment dev \
  --expected-updated-at '<fresh metadata timestamp with timezone>' \
  --attempt-id '<one UUID reserved for this authorized test>' \
  --receipt-dir '<existing private persistent directory>'
```

Preflight reads only the matching registration ID and requires the registration and account preference to be enabled. It validates build, environment, platform, update timestamp, existing APNs configuration, and the Gaia Eyes topic. It does not read a device token, sign a provider token, reserve an attempt, or send anything. Add `--execute` only for the specifically authorized send. The same predicates are checked again immediately before the transport call.

Use a retained private receipt directory on the same execution host. Before reading the token or calling APNs, the command exclusively creates and syncs the receipt file and its parent directory. An existing receipt blocks another attempt under that ID. Curl configuration files, URL globbing, and retries are disabled for this bounded one-shot call. Normal sender defaults are unchanged.

Never rerun an uncertain attempt with a new ID, another directory, another host, or a deleted receipt. A receipt on ephemeral storage cannot protect against a later execution on a replacement instance. Preserve the receipt and operator outcome before any instance replacement. There is no automatic retry, production deployment, or automatic or scheduled integration.

`accepted` means APNs returned HTTP 200; it does not prove that the phone displayed the notification. `rejected` reports an allowlisted provider reason without mutating the registration. `uncertain_do_not_retry` means receipt cannot be established and must not trigger another send. Provider bodies, errors, credentials, and device tokens are never printed.

Synthetic verification (no network/database/provider calls):

```sh
PYTHONPATH=. SUPABASE_DB_URL=postgresql://fixture:fixture@localhost/fixture \
  python -m pytest -q tests/bots/test_send_test_notification.py tests/bots/test_send_push_notifications.py
```

The tests exercise SQL recipient predicates against an in-memory database with two devices on one account and a third device on another account. They cover disabled preferences/registrations, stale metadata, revalidation, receipts, uncertain transport, secret redaction, fixed payload, provider rejection, and unchanged normal sender behavior.

## Authorized GitHub run on October 16, 2026

`phone-notification-test-20261016.yml` is a dedicated one-use manual workflow. It is fixed to this repository's numeric ID, the authorizing actor ID, `main`, its exact workflow path, build 9, development APNs, and SHA-256 fingerprints of the authorized account/registration IDs. Raw account/registration IDs and tokens are not published or logged. The operator supplies only the fresh registration update timestamp and the explicit confirmation input.

The first run, `38844659979`, stopped at the secret-free context guard because repository step debug logging was enabled; its sole APNs step was skipped. The owner explicitly approved disabling that Boolean logging setting and one replacement dispatch. Only native GitHub run number 2, attempt 1 may now execute. Run 1, run 3 or later, every rerun, other branches, forks, other actors, debug runs, and executions on or after October 17 UTC stop before sending. GitHub maintains these counters outside the runner. A fixed concurrency group adds serialization but is not the repeat-prevention mechanism.

Before loading database/APNs secrets, the job must successfully upload an immutable reservation artifact with `overwrite: false`. A second job execution within the same run cannot replace that artifact. The send step requires the successful upload's ID/digest plus the matching reservation file. This also fails closed if runner recreation loses local files. Artifact upload failure consumes the opportunity without sending. Missing final output or runner failure must be treated as uncertain and must never trigger another dispatch or rerun.

Before the replacement dispatch, verify the original run remains attempt 1 with its send step skipped, that no intervening workflow run exists, and that the exact phone metadata still matches. Abort if any condition has changed. The replacement uses a distinct attempt UUID and records the blocked predecessor in its reservation and terminal output.

The workflow identity must remain fixed. Do not rename, delete/recreate, reset counters, change the target, or extend the window to retry. GitHub does not document counter continuity across workflow recreation. Preserve the workflow ID, run ID, reservation artifact, and terminal result outside the runner; artifact retention is 90 days and cannot serve as a permanent ledger. A new test requires a separate explicit authorization and reviewed implementation.

The job uses only `contents: read`, pinned official actions, the existing pinned psycopg dependency, and existing APNs/database secrets scoped to the execution step. It makes no database writes. APNs HTTP 200 is provider acceptance only; confirm arrival with the phone owner separately.

Run the GitHub guard tests alongside the diagnostic tests:

```sh
PYTHONPATH=. SUPABASE_DB_URL=postgresql://fixture:fixture@localhost/fixture \
  python -m pytest -q tests/bots/test_send_test_notification.py \
  tests/bots/test_github_notification_test.py tests/bots/test_send_push_notifications.py
```
