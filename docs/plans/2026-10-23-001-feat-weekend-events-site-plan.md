# feat: Weekend family events site (static + scheduled refresh)

**Date:** 2026-10-23
**Status:** active
**Origin:** docs/brainstorms/2026-10-23-weekend-family-events-requirements.md

## Summary

No-build static site on GitHub Pages that reads `data/events.json` — a curated, family-ranked list of Triangle weekend events. A Python scraper pulls raw listings; a scheduled Devin session (Mon + Thu) runs the scraper, curates/ranks via LLM judgment, commits, and pushes.

## Architecture

```
scripts/fetch_events.py  →  data/raw_events.json  →  agent curation (REFRESH.md runbook)
                                                        → data/events.json
                                                            ↓
                                          index.html + app.js + styles.css (GitHub Pages)
```

- **Static frontend, no framework/build step.** `fetch('data/events.json')`, render cards grouped by day, sort by family score, filter chips (Free / Outdoor / town).
- **`data/events.json`** — the only contract between pipeline and site. Schema below.
- **`scripts/fetch_events.py`** — stdlib + requests/bs4 scrapers per source, emit `data/raw_events.json`.
- **`REFRESH.md`** — runbook the scheduled agent follows each run.

## Event schema (`data/events.json`)

```json
{
  "generated_at": "ISO-8601",
  "weekend": {"fri": "2026-10-23", "sun": "2026-10-25"},
  "events": [{
    "id": "slug", "title": "", "day": "fri|sat|sun",
    "start": "5:00 PM", "end": "7:00 PM",
    "venue": "", "city": "Cary", "cost": "Free|$x|Varies",
    "url": "", "source": "stufftodoinrdu",
    "ages": "all ages|5+", "indoor": false,
    "family_score": 92,
    "why": "one-line family sell",
    "tags": ["halloween","outdoor","free"]
  }]
}
```

## Key technical decisions

- **KTD1** — Vanilla JS over React/build tooling: zero deps, Pages-ready as-is, agent-editable forever.
- **KTD2** — Curation lives in `REFRESH.md` + scheduled Devin session, not GitHub Actions + paid LLM API (D4).
- **KTD3** — Scraper targets structured sources first (stufftodoinrdu vibe/city pages, kidsoutandabout ajax view); unstructured sources (Axios, parks & rec) are agent-read during curation, not scraped.
- **KTD4** — Dedup by normalized title + date; agent resolves fuzzy dupes across sources.

## Implementation units

### U1. Site + seed data

**Goal:** Working page with this weekend's real events (Oct 23–25), ranked.
**Files:** `index.html`, `styles.css`, `app.js`, `data/events.json`, `README.md`
**Approach:** Card grid grouped Fri/Sat/Sun, score badge, filter chips, "last updated" stamp. Seed events.json with ~25 curated events from the source survey.
**Verification:** Open index.html — ranked cards render, filters work, links out to sources.

### U2. Scraper

**Goal:** `python scripts/fetch_events.py` writes `data/raw_events.json`.
**Files:** `scripts/fetch_events.py`, `scripts/sources.yaml` (source list config)
**Approach:** Per-source fetch+parse with browser UA; tolerant parsing (skip on failure, log); normalize to the event schema minus score/why.
**Test expectation:** Manual run produces non-empty raw JSON; one broken source doesn't kill the run.

### U3. Refresh runbook + scheduling

**Goal:** Repeatable weekly curation a scheduled agent can execute unattended.
**Files:** `REFRESH.md`
**Approach:** Runbook steps: run scraper → read Axios weekly article + town calendars → merge/dedupe → score per rubric → write events.json → commit+push. Then `devin_schedule_manage` for Mon 7:00am + Thu 6:00pm ET.
**Verification:** Dry-run the runbook once; confirm a schedule exists.

### U4. Publish

**Goal:** Public URL on GitHub Pages.
**Approach:** `git init`, commit, create GitHub repo, push, enable Pages on `main` root. Needs `gh` CLI install or manual repo creation (no gh on machine).
**Verification:** URL serves the site with seeded data.

## Risks

- Source markup changes → scraper degrades gracefully (raw JSON empties, agent falls back to reading pages directly).
- GitHub auth isn't set up on this machine (no `gh`) → may need user action at U4.
- Scheduled Devin sessions consume ACUs — flagged for user confirmation at U3.
