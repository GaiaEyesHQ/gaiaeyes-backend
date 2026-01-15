# Gaia Eyes — Agent Operating Guide

This file defines how automation agents (Codex/ChatGPT/etc.) must work in this repo.

## Mandatory workflow
1. **Read first**: locate and review relevant files + existing docs before editing.
2. **Plan**: state a short plan when a task is non-trivial.
3. **Implement minimal diff**: prefer the smallest viable change.
4. **Run checks**: execute lint/tests/build where feasible.
5. **Document verification**: report what you ran and why.

## Prohibited behavior
- No refactors, renames, or rewrites unless explicitly requested.
- No new libraries/dependencies without approval.
- No new naming conventions or parallel data sources.
- No secret material added to docs or configs.

## Required output format (agent responses)
- Summary of changes.
- Files changed (list paths).
- Commands run + results.
- Verification steps the reviewer can take.

## Conventions to follow
- Backend API changes must follow patterns in `app/routers` + `app/security`.
- Supabase schema changes must be migration SQL in `supabase/migrations`.
- iOS changes must respect SwiftUI/AppState patterns.
- WordPress changes must stay within mu-plugins or theme overrides already in use.

## When in doubt
- **Do not guess.** Add a question to `docs/OPEN_QUESTIONS.md` with:
  - what’s unknown
  - why it matters
  - who can answer it / where to fill it in
