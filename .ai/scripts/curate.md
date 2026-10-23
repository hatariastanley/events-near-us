# scripts/curate.py

> Last updated: 2026-10-23 | Protection: STANDARD

## Purpose

Deterministic fallback curator: `data/raw_events.json` → `data/events.json`. Runs in the GitHub Actions cron (Mon+Thu) so the site updates even when no LLM pass happens.

## What It Does

Keyword/tag heuristics approximating the requirements rubric: kid keywords (+, capped 25), free (+12), family-friendly tag (+15), proximity to Holly Springs/Apex/Cary core (+12), scary (-22 + `scary` tag), adult keywords (-8/hit capped 24). Dedupes on normalized title, caps at 40 events. Undated events default to `days:["sat"]`; `why` left blank (LLM pass fills it).

## Agent Decisions / Thoughts

- **2026-10-23:** Exists because no Devin-schedule MCP tool was available — Actions cron is the automatic tier; REFRESH.md agent pass is the quality tier and overwrites this output.
