# data/events.json

> Last updated: 2026-10-23 | Protection: CRITICAL

## Purpose

THE contract between the refresh pipeline and the frontend — the curated, ranked weekend list.

## What It Does

`generated_at`, `weekend {fri,sun}`, `events[]` with `days` array, `family_score` (0–100), `why`, `tags`, `cost`, `indoor`, `city`, `venue`, `url`, `source`.

## Important Notes / NEVER Change

- Regenerated twice weekly by the REFRESH.md runbook — don't hand-edit between refreshes.
- `days` is an ARRAY (multi-day events render under each day) — changed from single `day` during initial build.
- Scores must reflect the requirements-doc rubric, seeded file is the reference example.
