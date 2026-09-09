# G-010 Active Work Checkpoint

Status: `review_ready_local`

The coordinator review at `20260908-G-010-coordinator-review.json` supersedes the earlier review-ready claim. Preserve the current edits in:

- `app/db/feedback.py`
- `app/db/migraine.py`
- `app/routers/symptoms.py`

Completed bounded verification:

1. **G-R12:** exercise a request-shaped non-autocommit connection after `SET`, prove a separate refresh connection sees committed writes, and prove commit failure rolls back atomically without refresh.
2. **G-R13:** exercise the actual prompt route for sequential and concurrent identical structured responses containing top-level `note_text` plus nested medicine; prove no duplicate canonical/history/detail/audit/prompt writes and stale mismatches cannot overwrite.
3. **G-R14:** prove the returned canonical episode note preview/count agrees with nested note save and explicit clear results.

The outdated API fixture now models the prompt preflight/lock/readback sequence.
The real request-path suite additionally asserts prompt, canonical update,
structured detail, and revision-audit contents.

Final commands:

```bash
PYTHONPATH=. DATABASE_URL=postgresql://localhost/test venv/bin/pytest -q tests/api/test_feedback.py tests/api/test_symptoms.py tests/services/test_migraine_follow_up.py tests/services/test_migraine_episode_contract.py
./scripts/run_migraine_postgres_tests.sh
```

Results: 31 focused tests passed; 63 disposable-PostgreSQL tests passed. Exact
database log:
`/Users/gennwu/.codex/test-logs/gaia-migraine-postgres/20260908T052329Z.log`.
Python compilation, runner shell syntax, and `git diff --check` also passed.

Boundaries: local disposable PostgreSQL only. No production access, remote SQL, migration push, deployment, client UI, release, physical-device work, or real user data.
