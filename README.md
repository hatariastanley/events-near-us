# Triangle Family Weekend

A static site that aggregates weekend (Fri–Sun) family events around the NC Triangle — Holly Springs, Apex, Cary, Fuquay-Varina, Raleigh, Durham, Knightdale — and ranks them by family appeal for kids ~5–10.

## How it works

```
scripts/fetch_events.py → data/raw_events.json → agent curation (REFRESH.md)
                                             → data/events.json → the site
```

- **Frontend:** vanilla HTML/CSS/JS, no build step. Reads `data/events.json`.
- **Pipeline:** Python scraper collects raw listings; a scheduled agent session (Mon + Thu) dedupes, scores, and writes `data/events.json` per `REFRESH.md`.
- **Hosting:** GitHub Pages, repo root on `main`.

## Woodcreek Community Events

The site includes a separate "Woodcreek" tab for events in the Woodcreek HOA community (Holly Springs, NC). These events are stored in `data/woodcreek_events.json` and are **never touched by the scraper or weekly refresh** — they're hand-edited from forwarded HOA emails/newsletters.

### Adding a Woodcreek event

Edit `data/woodcreek_events.json` and add an event object to the `events` array:

```json
{
  "id": "woodcreek-event-name-2026-12-15",
  "title": "Pool Party",
  "date": "2026-12-15",
  "day_of_week": "sun",
  "start": "2:00 PM",
  "end": "5:00 PM",
  "venue": "Woodcreek Clubhouse Pool",
  "cost": "Free for residents",
  "description": "End-of-year pool party with snacks and games for kids."
}
```

**Required fields:**
- `id` — Unique identifier (use format: `woodcreek-event-name-YYYY-MM-DD`)
- `title` — Event name
- `date` — Date in `YYYY-MM-DD` format (used for sorting and hiding past events)

**Optional fields:**
- `day_of_week` — e.g. "sun", "sat", "fri" (for display)
- `start` / `end` — Time (e.g. "2:00 PM")
- `venue` — Location within Woodcreek (e.g. "Woodcreek Clubhouse")
- `cost` — Price or leave empty if free
- `description` — Short description of the event

**Notes:**
- Past events (based on `date`) are automatically hidden from the site
- The `source_info` block at the top of the file tracks where events came from (e.g., which newsletter)
- The weekly scraper/LLM refresh never touches this file — it only updates `data/events.json`

## Local dev

```bash
python -m http.server 8000
# open http://localhost:8000
```

## Docs

- Requirements: `docs/brainstorms/2026-10-23-weekend-family-events-requirements.md`
- Plan: `docs/plans/2026-10-23-001-feat-weekend-events-site-plan.md`
- Weekly runbook: `REFRESH.md`
- Agent memory: `.ai/` (file-guardian convention — read before editing code)
