#!/usr/bin/env python3
"""Fetch raw event listings from Triangle-area sources -> data/raw_events.json.

Best-effort, tolerant scraping: one broken source never kills the run.
The agent curation step (REFRESH.md) cleans, dedupes, and ranks this output —
this script only needs to produce reasonable candidates.

Usage:  python scripts/fetch_events.py
Deps:   pip install -r requirements.txt
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing deps — run: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw_events.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TIMEOUT = 20


def upcoming_weekend(today=None):
    """Return (fri, sun) date objects for the coming/current weekend."""
    today = today or date.today()
    days_to_fri = (4 - today.weekday()) % 7  # Mon=0 ... Sun=6
    fri = today + timedelta(days=days_to_fri)
    return fri, fri + timedelta(days=2)


def get(url):
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def scrape_stufftodoinrdu():
    """Weekend page: event blocks with h3 title links, time, venue, vibes."""
    events = []
    soup = get("https://stufftodoinrdu.com/")
    for h3 in soup.select("h3 a[href*='/events/']"):
        block = h3.find_parent(["li", "article", "div"])
        text = block.get_text(" ", strip=True) if block else ""
        venue = block.select_one("a[href*='/venues/']") if block else None
        time = re.search(r"\d{1,2}(:\d{2})?\s*(AM|PM)", text)
        vibes = [a.get_text(strip=True) for a in block.select("a[href*='/is/']")] if block else []
        events.append({
            "title": h3.get_text(strip=True),
            "url": urljoin("https://stufftodoinrdu.com", h3.get("href", "")),
            "venue": venue.get_text(strip=True) if venue else "",
            "time_hint": time.group(0) if time else "",
            "cost": "Free" if "Free" in text else "",
            "source": "stufftodoinrdu",
            "tags": vibes,
        })
    return events


def scrape_kidsoutandabout():
    """Weekend roundup highlights (full list lives behind an iframe/ajax view)."""
    events = []
    for url in (
        "https://rt.kidsoutandabout.com/koaa_ajax_view/events/weekend-view",
        "https://rt.kidsoutandabout.com/content/things-do-weekend-and-around-triangle",
    ):
        try:
            soup = get(url)
        except Exception:
            continue
        for a in soup.select("a[href*='activity'], a[href*='event']"):
            title = a.get_text(" ", strip=True)
            if len(title) > 8:
                events.append({
                    "title": title, "url": urljoin(url, a.get("href", "")),
                    "venue": "", "time_hint": "", "cost": "",
                    "source": "kidsoutandabout", "tags": [],
                })
        if events:
            break
    return events


def scrape_triangleonthecheap():
    """Day tables: event | time | price | location. Needs browser UA."""
    events = []
    soup = get("https://triangleonthecheap.com/events/view-all/")
    for row in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cells) < 3:
            continue
        link = row.select_one("a[href]")
        events.append({
            "title": cells[0], "url": urljoin("https://triangleonthecheap.com", link["href"]) if link else "",
            "venue": cells[-1], "time_hint": cells[1] if len(cells) > 1 else "",
            "cost": cells[2] if len(cells) > 2 else "",
            "source": "triangleonthecheap", "tags": [],
        })
    return events


def scrape_raleighparent():
    """Events calendar listing links."""
    events = []
    soup = get("https://raleighparent.com/events/")
    for a in soup.select("a[href*='event']"):
        title = a.get_text(" ", strip=True)
        if len(title) > 8:
            events.append({
                "title": title, "url": urljoin("https://raleighparent.com", a.get("href", "")),
                "venue": "", "time_hint": "", "cost": "",
                "source": "raleighparent", "tags": [],
            })
    return events


SOURCES = {
    "stufftodoinrdu": scrape_stufftodoinrdu,
    "kidsoutandabout": scrape_kidsoutandabout,
    "triangleonthecheap": scrape_triangleonthecheap,
    "raleighparent": scrape_raleighparent,
}


def main():
    fri, sun = upcoming_weekend()
    collected, failed = [], []
    for name, fn in SOURCES.items():
        try:
            found = fn()
            print(f"{name}: {len(found)} listings")
            collected.extend(found)
        except Exception as exc:
            print(f"{name}: FAILED ({exc})", file=sys.stderr)
            failed.append(name)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weekend": {"fri": fri.isoformat(), "sun": sun.isoformat()},
        "failed_sources": failed,
        "raw_events": collected,
    }, indent=2, ensure_ascii=False))
    print(f"wrote {OUT} ({len(collected)} raw listings, {len(failed)} failed sources)")


if __name__ == "__main__":
    main()
