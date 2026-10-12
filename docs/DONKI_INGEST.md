# DONKI ingestion

`scripts/ingest_nasa_donki.py` ingests FLR and CME events into
`ext.donki_event` and optionally emits the existing `flares_cmes.json` format.

## Providers and credentials

- Primary: `https://api.nasa.gov/DONKI`
- Public fallback: `https://ccmc.gsfc.nasa.gov/DONKI-API/get`

NASA [announced the CCMC API migration](https://ccmc.gsfc.nasa.gov/news/major-updates/)
effective September 30, 2026. The API input parameters and response formats
remain unchanged. The old `kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get` address must
not be used. See the [DONKI tool page](https://ccmc.gsfc.nasa.gov/tools/DONKI/)
for the current API documentation.

`DONKI_BASE_PRIMARY` and `DONKI_BASE_FALLBACK` remain optional overrides.
Overrides must be base URLs without credentials, query strings, or fragments;
update any deployment-level fallback override as well as the code default.
`NASA_API_KEY` is sent only to an HTTPS primary whose exact hostname is
`api.nasa.gov` on the default HTTPS port. Fallbacks and other primary hosts
receive no key. Redirects are never followed, even if a caller enables them
on its HTTP client. Logs omit raw URLs, response bodies, and exception messages.

The existing required `SUPABASE_DB_URL` and `NASA_API_KEY`, date range,
day-mode, retry/backoff, and output-path settings remain supported.
Provider-specific retry counts still control HTTP 429/5xx and network retries.
Malformed JSON, error objects, invalid required event times, and malformed
identifiers or summary fields fail over to the next provider. Optional/null
fields and existing identifier/analysis aliases remain supported. A valid empty
list is a successful observation. A negative `START_DAYS_AGO` is rejected;
zero remains valid for today's events.

## Incomplete and empty ranges

Every requested FLR/CME slice must succeed before any database write or JSON
emission. If neither provider can serve a requested slice, the process exits nonzero;
even previously downloaded slices are not written. Existing database rows and
JSON bytes/timestamp are preserved. This favors last-known-good output over
publishing a partial range as an apparently complete summary. Existing
consumers can use the unchanged JSON timestamp to assess freshness.

A fully successful empty range skips database writes and emits a fresh empty
summary, clearing an obsolete dashboard summary. The existing optional GOES
flare-max supplement still applies. GOES failure does not invalidate a complete
DONKI result. The top-level JSON format is unchanged, and source strings now
identify the successful provider URLs (comma-separated if daily slices used
both providers), without query parameters or API keys.

The scheduled `nasa-donki` workflow stops after a nonzero ingest exit, so its
ordinary later media-publish steps do not run with incomplete data. This change
does not alter that workflow, deployment settings, migrations, or DB schema.
The shared JSON supplies web/app consumers, so no separate UI change is needed.

## Verification

Run the isolated regression suite on Python 3.11:

```sh
python -m pytest -q tests/scripts/test_ingest_nasa_donki.py
```

Tests use synthetic credentials, `httpx.MockTransport`, and mocked database
connections. They never read production credentials or contact a live service.
Coverage includes primary/fallback success, redirects, host validation,
HTTP/network retry exhaustion, malformed payloads, secret-safe diagnostics,
empty ranges, incomplete daily/range results, gzip preservation, and CLI failure.
`.github/workflows/donki-ingest-tests.yml` runs this suite with read-only
repository permissions and no production secrets or database service.
