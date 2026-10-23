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
