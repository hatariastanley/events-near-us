# scripts/curate.py

> Last updated: 2026-10-23 | Protection: STANDARD

## Purpose

Deterministic fallback curator: `data/raw_events.json` → `data/events.json`. Runs in the GitHub Actions cron (Mon+Thu) so the site updates even when no LLM pass happens.

## What It Does

Keyword/tag heuristics approximating the requirements rubric: kid keywords (+, capped 25), free (+12), family-friendly tag (+15), proximity to Holly Springs/Apex/Cary core (+12), scary (-22 + `scary` tag), adult keywords (-8/hit capped 24). Dedupes on normalized title, caps at 40 events. Undated events default to `days:["sat"]`; `why` left blank (LLM pass fills it).

## Agent Decisions / Thoughts

- **2026-10-23:** Exists because no Devin-schedule MCP tool was available — Actions cron is the automatic tier; REFRESH.md agent pass is the quality tier and overwrites this output.

## Bug fix — 2026-11-13 (out-of-window events + blob cleanup)

**Symptom:** Nov 20/21/24 and Dec 19 events appeared in the Nov 13–15 list;
day grouping was wrong (everything defaulted sat).
**Cause:** no date filtering — raw titles carried the date but it was never
parsed against the weekend window.
**Fix:** curate extracts `date_hint`/`day_hint` from raw fields OR from the
title prefix (`Day, Mon dd` / `Mon dd(-dd)` ranges), maps through
`weekend_day_map()` and SKIPS dated events outside Fri–Sun. Multi-day
ranges produce multiple `days`. `clean_title()` strips prefix debris +
`mi away` tails as a safety net for any source.

**Note:** the `�` chars in console output are a Windows-terminal rendering
artifact — JSON data is correct UTF-8 (S’mores uses U+2019, Axé uses U+00E9).
`fix_mojibake()` remains as a guard for real U+FFFD cases.

**Source health 2026-11-13:** stufftodoinrdu now blocks GH runner IPs too
(serves isolation page); triangleonthecheap still 403. Live data currently
= raleighparent (~309) + kidsoutandabout (~3). Coverage regression — worth
revisiting sources or adding town-parks calendars.
