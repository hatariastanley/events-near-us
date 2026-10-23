# Weekend Family Events Site — Requirements

**Date:** 2026-10-23
**Status:** Draft

## Problem

Finding family-friendly weekend events around the southwestern Triangle (Holly Springs, Apex, Cary, Fuquay-Varina, plus Raleigh/Durham/Knightdale) means checking a half-dozen websites every week. We want one page that aggregates them, pre-ranked for what a family actually cares about, refreshed automatically.

## Users

- **A1 — Parent** planning the weekend for a family with kids ~5–10 (also wants whole-family appeal).

## Requirements

- **R1** — Aggregate weekend events (Fri–Sun) from Triangle-area third-party sources.
- **R2** — Cover the area: Holly Springs, Apex, Cary, Fuquay-Varina, Morrisville, Raleigh, Durham, Knightdale, Wake Forest, Garner, Chapel Hill/Carrboro (further = lower rank, not excluded).
- **R3** — Rank events by family appeal, optimized for kids ~5–10 and whole-family-mixed appeal.
- **R4** — Present as a website: per-event title, day/time, venue, town, cost, link, short "why it's good for families", and rank/score.
- **R5** — Refresh cadence: **Monday morning** (early-planning pass) + **Thursday evening** (top-up once weekly roundups publish).
- **R6** — Hosting: GitHub Pages (free, public URL).
- **R7** — Data pipeline is *hybrid*: a scraper collects raw listings; an agent curation step dedupes, normalizes, and applies the family ranking.

## Key decisions

- **D1** — Hybrid collection over pure scraper: event pages are inconsistent; an LLM curation step gives better dedupe + ranking quality. Chosen by user.
- **D2** — GitHub Pages over local file: shareable URL, free, auto-deploys on push.
- **D3** — Mon + Thu refresh: Monday for planning, Thursday for freshest data (Axios/roundups drop Thu/Fri).
- **D4** — The curation step runs as a **scheduled Devin session** (not a paid LLM API in GitHub Actions): no API key to manage, agent can run the scraper + curate + push in one run.

## Ranking rubric (family-fit score 0–100)

| Signal | Weight |
|--------|--------|
| Kid appeal for ages ~5–10 (hands-on, animals, festivals, trains, museums) | 35 |
| Whole-family appeal (parents enjoy it too) | 20 |
| Cost (free = max, then scaled) | 15 |
| Ease (drop-in, no registration, short commitment, easy parking) | 15 |
| Proximity to Holly Springs/Apex/Cary core | 15 |

## Sources (initial set)

| Source | Type | Notes |
|--------|------|-------|
| stufftodoinrdu.com | Structured HTML | Best source — vibe tags (`family-friendly`, `free`), city pages, clean markup |
| rt.kidsoutandabout.com | HTML + iframe ajax view | Family-specific; weekend roundup + free-events lists |
| raleighparent.com/events | Calendar HTML | The "parent" calendar; category + price tagged |
| triangleonthecheap.com/events | Table HTML | Day-by-day tables; may need UA header (403s on naive fetch) |
| axios.com/local/raleigh | Weekly article | "What to do this weekend" — Thu; agent-read, not scraped |
| Town parks & rec (Holly Springs, Apex, Cary) | Varied | Add incrementally |

## Scope boundaries

- Weekend window = Friday 12pm → Sunday midnight.
- **Deferred:** user accounts/favorites, email digest, maps view, weekday events, weather integration.
- **Out:** ticketing/booking, non-Triangle events.

## Success criteria

- Site loads at a public Pages URL showing this weekend's ranked events.
- A refresh run updates `data/events.json` and deploys without manual edits.
- List visibly favors the kind of events a family with a 5–10-year-old would pick over e.g. 21+ nightlife.
