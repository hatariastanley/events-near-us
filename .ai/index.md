# index.html

> Last updated: 2026-10-23 | Protection: STANDARD

## Purpose

The whole site — single static page rendering ranked weekend family events.

## What It Does

Masthead (kicker, title, tagline, updated stamp) → filter chips → three day sections (Fri/Sat/Sun) → footer crediting sources. All rendering happens in `app.js`; this file is structure only.

## Dependencies

- `styles.css` — warm fall editorial theme (Fraunces + Work Sans via Google Fonts)
- `app.js` — fetches `data/events.json`, owns all DOM writing

## Important Notes / NEVER Change

- Keep `id` attributes (`filters`, `cards-fri|sat|sun`, `date-*`, `updated-stamp`, `empty-state`, `events-root`) — app.js binds to them.
- No framework/build — intentional (see .ai/PROJECT_CONTEXT.md decisions).
