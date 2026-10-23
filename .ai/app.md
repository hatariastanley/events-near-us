# app.js

> Last updated: 2026-10-23 | Protection: STANDARD

## Purpose

Fetches `data/events.json` and renders ranked event cards grouped by day, with filter chips.

## What It Does

- Loads events.json; stamps header with `generated_at` + event count; fills day dates.
- Renders each event under every day in its `days` array (multi-day events repeat).
- Sorts by `family_score` desc; score ≥85 gets the accent "top" badge color.
- Filters: all / free / outdoor / indoor / nearby (NEARBY_TOWNS) / gentle (excludes `scary`/`21+` tags).

## Important Notes / NEVER Change

- `data/events.json` schema is THE contract (fields: `days[]`, `family_score`, `why`, `tags`, `cost`, `indoor`, `city`, `url`…). Changing names breaks the pipeline + REFRESH.md together.
- `NEARBY_TOWNS` defines the "Near home" filter — user's core area.
- HTML-escape everything from JSON (`escapeHtml`).
