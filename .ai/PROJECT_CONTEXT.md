# Project Context

> **AI MUST READ THIS BEFORE ANY CODE MODIFICATION**
> On resume / new session: read this FIRST, then the file mirrors you will touch.

## Overview

- **Project name:** Events Near Us — weekend family events aggregator for the NC Triangle
- **Tech stack:** Static site (vanilla HTML/CSS/JS, no build) + Python 3 scraper
- **Audience:** Parent planning weekends for a family, kids ~5–10
- **Hosting:** GitHub Pages (serves repo root on `main`)

## Architecture

`scripts/fetch_events.py` → `data/raw_events.json` → agent curation (`REFRESH.md` runbook, scheduled Mon+Thu) → `data/events.json` → static frontend renders ranked cards.

## Directory Structure

```
index.html, styles.css, app.js   # the site (no build step)
data/events.json                 # curated, ranked events — THE contract
data/raw_events.json             # scraper output (generated, may not exist yet)
scripts/fetch_events.py          # source scrapers
scripts/sources.yaml             # source list config
REFRESH.md                       # runbook for weekly agent refresh
docs/brainstorms/                # requirements doc
docs/plans/                      # implementation plan
.ai/                             # this mirror
```

## Current Work

- 2026-10-23: Initial build — site, seeded events.json (Oct 23–25 weekend), scraper, runbook, Pages publish.
- Open: GitHub repo not yet created (no `gh` CLI on machine); scheduled refresh not yet configured.

## Global Rules

1. `data/events.json` is the ONLY contract between pipeline and frontend — schema defined in the plan doc.
2. No build tooling; keep the site dependency-free.
3. Scraper must never hard-fail the whole run on one bad source.
4. Family ranking rubric lives in the requirements doc (kid appeal 35 / family appeal 20 / cost 15 / ease 15 / proximity 15).

## Protected Files

| File | Level | Why |
|------|-------|-----|
| data/events.json | CRITICAL | Site breaks if schema changes without updating app.js |
| REFRESH.md | PROTECTED | Scheduled agent depends on it weekly |

## Agent Decisions / Thoughts

- **2026-10-23:** Chose Devin scheduled sessions over GitHub Actions + LLM API for curation — no API key management, agent reads messy sources well.
- **2026-10-23:** Vanilla JS, no framework — zero deps, Pages-ready, durable.

## Important Notes / NEVER Change

- Weekend window = Friday noon → Sunday night.
- Never drop the `family_score`/`why` fields — ranking is the product's point.
