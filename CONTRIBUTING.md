# Contributing to Gaia Eyes

## Local development
### Backend (FastAPI)
1. Create a venv and install deps.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Configure `.env` using `.env.example` (see `docs/ENVIRONMENT_VARIABLES.md`).
3. Run the API:
   ```bash
   uvicorn app.main:app --reload
   ```

### Supabase (local, optional)
- See `docs/SUPABASE.md` for `supabase` CLI expectations and schema notes.

### WordPress
- This repo contains only `wp-content/` (no WP core). Bring your own WordPress install and mount/copy `wp-content` in.
- Configure env vars for mu-plugins (see `docs/ENVIRONMENT_VARIABLES.md`).

### iOS
- Build instructions are in `docs/IOS_APP.md` and `gaiaeyes-ios/ios/README_iOS.md`.

## Branching + PRs
- Create a feature branch per task.
- Keep diffs minimal and focused.
- Update docs when behavior or env vars change.

## Linting/tests
- Backend: run existing tests/lints from `requirements.txt` (see `docs/BACKEND.md`).
- iOS: use Xcode build/test commands documented in `docs/IOS_APP.md`.
- WordPress: no automated tests in repo — validate manually.

## Adding features
### Backend endpoints
- Add new routes in `app/routers/` and include them in `app/main.py`.
- Keep auth/authorization consistent with `app/security/auth.py`.

### iOS screens
- Follow MVVM/ObservableObject pattern in `gaiaeyes-ios/ios/GaiaExporter`.

### WordPress integrations
- Prefer mu-plugins in `wp-content/mu-plugins` for shortcodes/data access.

## Supabase schema changes
- Always add a new migration under `supabase/migrations`.
- Document new tables/columns in `docs/SUPABASE.md` and `docs/ENVIRONMENT_VARIABLES.md`.
