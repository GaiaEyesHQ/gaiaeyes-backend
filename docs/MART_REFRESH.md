# Mart refresh-on-ingest

GaiaEyes now refreshes the daily features mart as soon as new samples arrive. The `/v1/samples/batch` handler schedules a background task after it successfully inserts a batch for a single user.

## How it works

1. The caller can include `?tz=<IANA name>` (default `America/Chicago`). The server converts the current time into that timezone to determine the local day.
2. After committing the batch, the handler debounces refreshes per user. Additional batches within ~20 seconds reuse the existing refresh ticket.
3. The refresh runs from a background coroutine that sleeps for two seconds before executing `select marts.refresh_daily_features_user(:user_id, :day_local);`, giving pgBouncer time to settle after a large ingest burst.
4. Scheduling and failures are logged with the `[MART]` prefix for quick tailing (`[MART] scheduled refresh (delayed) ...`).

The debounce map lives in-process, so each worker independently guards its refresh cadence.

## Disabling during load tests

Set the environment variable `MART_REFRESH_DISABLE=1` (accepted truthy values: `1`, `true`, `yes`, `on`) to bypass scheduling without redeploying code. The handler logs a skip message and continues inserting samples normally.

## Testing hooks

`app/routers/ingest.py` exposes `_refresh_task_factory` and `_execute_refresh`. Tests can monkeypatch these helpers to run synchronously or capture scheduled users, enabling deterministic assertions without touching the real database.
