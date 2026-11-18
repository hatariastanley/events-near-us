# Weekly Refresh Runbook

Two refresh tiers:

1. **Automatic (baseline):** `.github/workflows/refresh.yml` runs the scraper + `scripts/curate.py` on GitHub Actions every **Mon 7am + Thu 6pm ET** and commits `data/events.json`. Deterministic ranking — decent, not great.
2. **Agent pass (better):** the runbook below. An LLM curation run produces real `why` text, accurate day assignments, and better dedupe. Run it whenever you want a better list — it overwrites the Actions output.

## Agent runbook (the LLM pass)

1. **Collect raw listings**
   ```bash
   pip install -r requirements.txt   # first run only
   python scripts/fetch_events.py --days 90
   ```
   Check `data/raw_events.json`. If `failed_sources` is non-empty, note which sources broke — the curation step compensates by reading them directly. If `partial_sources` is non-empty, treat that source's coverage as incomplete and fill gaps directly.

2. **Read non-scraped sources directly** (these publish late-week or resist scraping):
   - Axios Raleigh "what to do this weekend" — search `site:axios.com/local/raleigh what to do this weekend`
   - Town of Cary / Apex / Holly Springs parks & rec event calendars
   - `data/raw_events.json` for everything else

3. **Merge + dedupe.** Same event appearing on multiple sources → keep one entry, prefer the canonical event/venue URL. Never fabricate a URL — when no direct event page exists, link the source's listing page.

4. **Normalize + rank** into the `data/events.json` schema (see `docs/plans/`). For each event write:
   - `days` — array subset of `["fri","sat","sun"]` for weekend events; use `[]` for dated events outside this weekend
   - `date` — ISO `YYYY-MM-DD` for every event with a known date (required for the upcoming-weekend views)
   - `family_score` — per the rubric in `docs/brainstorms/` (kid appeal ~5–10: 35, whole-family appeal: 20, cost: 15, ease/drop-in: 15, proximity to Holly Springs/Apex/Cary: 15)
   - `why` — one sentence, the honest family sell (mention trade-offs: cost, scare factor, crowds)
   - `tags` — include `scary` for haunts/spooky events and `free` where applicable
   - Scary/adult events stay in the list but score low — parents want to know they exist, not have them hidden.

5. **Write `data/events.json`** with fresh `generated_at` (local ISO time), `weekend` dates (next Fri–Sun), and `range` covering the next 90 days.

6. **Commit and push:**
   ```bash
   git add data/events.json data/raw_events.json
   git commit -m "Refresh weekend events (Fri–Sun)"
   git push
   ```
   GitHub Pages redeploys automatically.

## Guardrails

- Always verify a suspicious listing against its source page before including it.
- Prefer broad coverage: enough dated weekend events to make the upcoming-weekend selector useful, ranked, not a firehose.
- If the scraper output looks empty/broken, still produce the list by reading sources directly — the scraper is a convenience, not a dependency.
- **Never touch `data/woodcreek_events.json`** — it's hand-edited for HOA community events and is completely separate from the scraper/curation pipeline.
