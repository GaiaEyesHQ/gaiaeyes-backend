# Codex Task: Seed Home Feed Facts, Tips, and Messages

## Goal
Create a production-ready content seed for the iOS Home feed card backed by `content.home_feed_items`.

The card appears once per user per day, only when the user has an unseen active item for their selected mode. If no new item exists, the card stays hidden.

## Table
Use `content.home_feed_items`.

Important fields:
- `slug`: stable unique identifier, lowercase kebab-case.
- `mode`: `scientific`, `mystical`, or `all`.
- `kind`: `fact`, `tip`, or `message`.
- `title`: short headline, ideally under 45 characters.
- `body`: one concise paragraph, ideally 120-220 characters.
- `link_label`: optional.
- `link_url`: optional.
- `active`: true for live items.
- `priority`: higher numbers appear earlier.
- `starts_at` / `ends_at`: optional scheduling.

## Content Direction
Scientific mode should feel educational, practical, and evidence-aware:
- Explain what Gaia Eyes watches.
- Clarify limits without sounding defensive.
- Avoid diagnosis or treatment claims.
- Prefer "can line up with" or "may overlap with" over causal claims.

Mystical mode should feel grounded, poetic, and calm:
- Use nature/Gaia language without implying certainty.
- Keep the same truth layer as scientific mode.
- Avoid fear, urgency, prophecy, or medical advice.

All-mode tips should support app use:
- Why context flags matter.
- Why symptom logs improve personalization.
- Why location and sleep context help.

## Minimum Seed
Create at least:
- 30 scientific facts or tips.
- 30 mystical messages.
- 15 all-mode practical tips.

## Output
Produce a migration SQL file that inserts or updates rows by `slug`.

Use this pattern:

```sql
insert into content.home_feed_items (slug, mode, kind, title, body, priority)
values
  (...)
on conflict (slug) do update
set mode = excluded.mode,
    kind = excluded.kind,
    title = excluded.title,
    body = excluded.body,
    priority = excluded.priority,
    active = true,
    updated_at = now();
```

## Quality Rules
- No medical diagnosis.
- No guaranteed causation.
- No repetitive phrasing across items.
- No long essays.
- No links unless the destination exists and is stable.
- Keep punctuation simple and app-card friendly.
