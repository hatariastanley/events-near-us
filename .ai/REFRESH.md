# REFRESH.md

> Last updated: 2026-10-23 | Protection: PROTECTED

## Purpose

The weekly runbook a scheduled agent executes Mon ~7am + Thu ~6pm ET to regenerate `data/events.json`.

## What It Does

Scrape → read non-scraped sources (Axios, town calendars) → dedupe → score per rubric → write events.json → commit/push → Pages redeploys.

## Important Notes / NEVER Change

- Ranking rubric weights live in `docs/brainstorms/` — score against those, don't improvise.
- Never fabricate event URLs; link the source listing page instead.
- Scary/adult events stay in the list (low score + `scary` tag) — don't silently drop.
