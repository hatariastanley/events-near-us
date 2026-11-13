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

try:
    import truststore
    truststore.inject_into_ssl()  # corporate TLS-inspection proxies: use the OS cert store
except ImportError:
    pass

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
    if "Browser Isolation" in r.text or "Zscaler" in r.text[:5000]:
        # Corporate TLS proxy serving an isolation wrapper instead of the page.
        # Expected behind Zscaler; works fine from non-proxied networks (CI/cloud).
        raise RuntimeError("blocked by proxy browser isolation")
    return BeautifulSoup(r.content, "html.parser")  # let bs4 sniff meta charset (avoids � mojibake)


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
            "day_hint": heading_day(h3),
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


RP_HEAD = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Z][a-z]{2}\s+\d{1,2}),\s+"
    r"(?:(\d{1,2}:\d{2}\s*[AP]M)(?:\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?\s+)?(.*)$")
DAY_MAP = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
           "fri": "fri", "sat": "sat", "sun": "sun"}


def scrape_raleighparent():
    """Events calendar. Link text is a blob: 'Fri, Nov 20, 05:00 PM - 08:00 PM
    <title> at <venue>, <city> 891.9 mi away • FREE • <categories>'.
    Keep only date-prefixed links (drops nav junk), then split the blob."""
    events = []
    soup = get("https://raleighparent.com/events/")
    for a in soup.select("a[href*='event']"):
        blob = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        m = RP_HEAD.match(blob)
        if not m:
            continue
        wday, date_hint, start, end, rest = m.groups()
        body, _, tail = rest.partition(" mi away")
        body = re.sub(r"\s*\d+(\.\d+)?$", "", body).strip()
        title, sep, venue = body.rpartition(" at ")
        if not sep or len(title) < 4:
            title, venue = body, ""
        cost = ""
        for seg in re.split(r"[•�]", tail):
            seg = seg.strip(" -")
            if re.match(r"(?i)(free|\$)", seg):
                cost = seg[:60]
                break
        if len(title) < 5:
            continue
        events.append({
            "title": title,
            "url": urljoin("https://raleighparent.com", a.get("href", "")),
            "venue": venue.strip(),
            "time_hint": start or "",
            "time_end": end or "",
            "cost": cost,
            "source": "raleighparent",
            "tags": [],
            "day_hint": DAY_MAP[wday.lower()],
            "date_hint": date_hint,
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
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(collected)} raw listings, {len(failed)} failed sources)")


if __name__ == "__main__":
    main()
