# scripts/fetch_events.py

> Last updated: 2026-10-23 | Protection: STANDARD

## Purpose

Collects raw event listings from Triangle sources → `data/raw_events.json`.

## What It Does

Per-source scrapers (requests + BeautifulSoup, browser UA): stufftodoinrdu (h3 event links + venue/vibe tags), kidsoutandabout (ajax weekend view → content page fallback), triangleonthecheap (day tables), raleighparent (event links). Computes upcoming Fri–Sun. Each source is try/except isolated — failures logged to `failed_sources`, run continues.

## Important Notes / NEVER Change

- NEVER let one source failure kill the run (global rule).
- Output is input to agent curation (REFRESH.md) — raw/partial is acceptable; precision happens downstream.
- triangleonthecheap 403s without a realistic User-Agent.

## Bug Fixes

| Date | Bug | Cause | Fix |
|------|-----|-------|-----|
| 2026-10-23 | All sources failed SSL verify | Corporate Zscaler TLS inspection — Python certifi lacks the corp root CA | `truststore.inject_into_ssl()` to use the OS cert store |
| 2026-10-23 | stufftodoinrdu returned 0 listings | Zscaler serves a "Browser Isolation" iframe wrapper for that domain locally | Detect wrapper → raise "blocked by proxy" (works from non-proxied/cloud runs) |
| 2026-10-23 | UnicodeEncodeError writing JSON | Windows default cp1252 encoding | `write_text(..., encoding="utf-8")` |

## Bug fix — 2026-11-13 (listing blob pollution)

**Symptom:** Live cards showed titles like "Jazz & Jive Night at The Depot
parking lot, Apex 891.9 mi away • FREE • Family Dance Live Music…".
**Cause:** `scrape_raleighparent` grabbed every `a[href*='event']` including
nav links, and raleighparent link text is a structured blob
(`Day, Mon dd, times <title> at <venue>, <city> <crawler-distance> mi away
• cost • categories`). The "NNN mi away" was distance from THEIR crawler,
not the user. `curate.py` passed it through.
**Fix:** only accept links matching `Day, Mon dd,` prefix (drops ~140 nav
entries); split blob via `RP_HEAD` regex + ` mi away` partition into
title/venue/time_hint/time_end/cost/day_hint/date_hint. Also: `get()` now
feeds `r.content` to BeautifulSoup (meta-charset sniffing); stufftodoinrdu
entries get `day_hint` from the nearest preceding day heading.
