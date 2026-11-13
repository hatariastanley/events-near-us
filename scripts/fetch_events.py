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


def _date_hint(d):
    return f"{d.strftime('%b')} {d.day}"


def scrape_civicplus(source_name, base, city):
    """CivicPlus month-grid calendar. Each day cell links an eventDetails
    tooltip: <div name="showDetailsBox" id="showDetails<EID>_<n>"> with
    h3 title, dt/dd When+Location, and a 'More Details' href carrying
    ?EID=&month=&year=&day=. Category lives in the grid anchor's
    .visuallyHidden span right before the tooltip."""
    events = []
    soup = get(f"{base}/calendar.aspx?view=list")
    items = soup.select(".calendars .calendar ol li")
    if items:
        for li in items:
            nm = li.select_one('[itemprop="name"]')
            st = li.select_one('[itemprop="startDate"]')
            a = li.select_one("h3 a[href]")
            if not (nm and a):
                continue
            title = nm.get_text(" ", strip=True)
            if len(title) < 5:
                continue
            day_hint = date_hint = time_hint = ""
            if st:
                try:
                    dt = datetime.fromisoformat(st.get_text(strip=True))
                    day_hint = dt.strftime("%a").lower()[:3]
                    date_hint = _date_hint(dt.date())
                    time_hint = dt.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    pass
            loc = li.select_one('span[itemprop="location"] [itemprop="name"]')
            group = li.find_parent(class_="calendar")
            gtitle = group.select_one("h2.title").get_text(strip=True)                 if group and group.select_one("h2.title") else ""
            events.append({
                "title": title,
                "url": urljoin(base, a["href"]),
                "venue": loc.get_text(" ", strip=True) if loc else "",
                "time_hint": time_hint, "time_end": "",
                "cost": "", "source": source_name, "city": city,
                "tags": [gtitle] if gtitle else [],
                "day_hint": day_hint, "date_hint": date_hint,
            })
        if events:
            return events
    fri, _ = upcoming_weekend()
    months = {(fri.month, fri.year), ((fri + timedelta(days=2)).month,
                                      (fri + timedelta(days=2)).year)}
    for month, year in months:
        soup = get(f"{base}/calendar.aspx?month={month}&year={year}")
        for tip in soup.select('div[name="showDetailsBox"]'):
            a = tip.find("a", href=re.compile(r"EID=\d+"))
            q = {}
            if a:
                for part in a["href"].split("?", 1)[-1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        q[k] = v
            try:
                ev = date(int(q["year"]), int(q["month"]), int(q["day"]))
            except Exception:
                continue
            h3 = tip.find("h3")
            title = h3.get_text(" ", strip=True) if h3 else ""
            title = re.sub(r"^\d{1,2}:\d{2}\s*[AP]M\s*", "", title).rstrip(":").strip()
            if len(title) < 5:
                continue
            dts, dds = tip.find_all("dt"), tip.find_all("dd")
            meta = {dt.get_text(strip=True).rstrip(":"): dd.get_text(" ", strip=True)
                    for dt, dd in zip(dts, dds)}
            when = meta.get("When", "")
            tm = re.match(r"(\d{1,2}:\d{2}\s*[AP]M)", when)
            te = re.search(r"-\s*(\d{1,2}:\d{2}\s*[AP]M)", when)
            cat = ""
            prev = tip.find_previous("a")
            if prev:
                vh = prev.find(class_="visuallyHidden")
                if vh:
                    cat = vh.get_text(strip=True).replace("Category:", "").strip()
            events.append({
                "title": title,
                "url": urljoin(base, a["href"]) if a else base + "/calendar.aspx",
                "venue": meta.get("Location", ""),
                "time_hint": tm.group(1) if tm else "",
                "time_end": te.group(1) if te else "",
                "cost": "", "source": source_name, "city": city,
                "tags": [cat] if cat else [],
                "day_hint": ev.strftime("%a").lower()[:3],
                "date_hint": _date_hint(ev),
            })
    return events


def scrape_wakegov(pages=4):
    """wake.gov/events — Drupal responsive-grid cards covering ALL Wake
    County events incl. every library branch's storytimes and county park
    programs. Card: h2 a title/link, .date-time range text, trailing
    dept/audience text."""
    events = []
    for pg in range(pages):
        soup = get(f"https://www.wake.gov/events?page={pg}")
        grid = soup.select_one(".views-view-responsive-grid")
        if not grid:
            break
        cells = grid.find_all(True, recursive=False)
        if not cells:
            break
        for cell in cells:
            card = cell.select_one(".event--card, .card") or cell
            h2a = card.select_one("h2 a")
            if not h2a:
                continue
            title = h2a.get_text(" ", strip=True)
            url = urljoin("https://www.wake.gov", h2a.get("href", ""))
            dt_el = card.select_one(".date-time")
            dt_text = dt_el.get_text(" ", strip=True) if dt_el else ""
            dm = re.search(r"(\w+day),?\s+(\w+)\s+(\d{1,2}),\s+(\d{4})", dt_text)
            tm = re.search(r"(\d{1,2}:\d{2}\s*[ap]m)", dt_text, re.I)
            tail = card.get_text(" ", strip=True)
            tail = tail.replace(title, "", 1).replace(dt_text, "").strip()
            day_hint = date_hint = ""
            if dm:
                mon = {"january": 1, "february": 2, "march": 3, "april": 4,
                       "may": 5, "june": 6, "july": 7, "august": 8,
                       "september": 9, "october": 10, "november": 11,
                       "december": 12}.get(dm.group(2).lower())
                if mon:
                    ev = date(int(dm.group(4)), mon, int(dm.group(3)))
                    day_hint = ev.strftime("%a").lower()[:3]
                    date_hint = _date_hint(ev)
            events.append({
                "title": title, "url": url,
                "venue": "", "time_hint": tm.group(1) if tm else "",
                "time_end": "", "cost": "", "source": "wakegov",
                "tags": [tail] if tail else [],
                "day_hint": day_hint, "date_hint": date_hint,
            })
    return events


def scrape_tec(source_name, base, per_page=30):
    """WordPress 'The Events Calendar' REST API — clean JSON.
    /wp-json/tribe/events/v1/events?start_date&end_date"""
    fri, sun = upcoming_weekend()
    r = requests.get(
        f"{base}/wp-json/tribe/events/v1/events",
        params={"start_date": fri.isoformat(), "end_date": sun.isoformat(),
                "per_page": per_page, "status": "publish"},
        headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    events = []
    for e in r.json().get("events", []):
        start = e.get("start_date", "")
        day_hint = date_hint = time_hint = ""
        try:
            dt = datetime.fromisoformat(start.replace(" ", "T"))
            day_hint = dt.strftime("%a").lower()[:3]
            date_hint = _date_hint(dt.date())
            time_hint = dt.strftime("%I:%M %p").lstrip("0") if (dt.hour or dt.minute) else ""
        except Exception:
            pass
        venue = e.get("venue") or {}
        cost = e.get("cost", "") or ""
        if isinstance(cost, list):
            cost = cost[0] if cost else ""
        cats = [c.get("name", "") for c in e.get("categories", []) if isinstance(c, dict)]
        events.append({
            "title": BeautifulSoup(e.get("title", ""), "html.parser").get_text(),
            "url": e.get("url", ""),
            "venue": venue.get("venue", "") if isinstance(venue, dict) else "",
            "time_hint": time_hint, "time_end": "", "cost": str(cost),
            "source": source_name,
            "city": venue.get("city", "") if isinstance(venue, dict) else "",
            "tags": [t for t in cats if t],
            "day_hint": day_hint, "date_hint": date_hint,
        })
    return events


def scrape_fun4raleighkids():
    """fun4raleighkids.com — Joomla JEvents. Day-list pages are server
    rendered: /calendar/day.listevents/YYYY/M/D/- with .jev_listrow rows."""
    events = []
    fri, _ = upcoming_weekend()
    days = [fri, fri + timedelta(days=1), fri + timedelta(days=2)]
    for day in days:
        soup = get(f"https://fun4raleighkids.com/calendar/day.listevents/{day.year}/{day.month}/{day.day}/-")
        for row in soup.select(".jev_listrow"):
            a = row.select_one("h2 a[href]")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            if len(title) < 5:
                continue
            def field(cls):
                li = row.select_one(cls)
                return li.get_text(" ", strip=True) if li else ""
            t = field(".f4us_time")
            tm = re.search(r"(\d{1,2}:\d{2}\s*[ap]m)", t, re.I)
            cost = re.sub(r"^Cost:\s*", "", field(".f4us_cost"))[:60]
            loc = re.sub(r"^Location:\s*", "", field(".f4us_location"))[:120]
            events.append({
                "title": title,
                "url": urljoin("https://fun4raleighkids.com", a["href"]),
                "venue": loc,
                "time_hint": tm.group(1) if tm else "",
                "time_end": "", "cost": cost or ("Free" if "free" in row.get_text().lower() else ""),
                "source": "fun4raleighkids", "tags": ["family"],
                "day_hint": day.strftime("%a").lower()[:3],
                "date_hint": _date_hint(day),
            })
    return events


CIVICPLUS_SITES = {
    "hollysprings":   ("https://www.hollyspringsnc.us", "Holly Springs"),
    "apex":           ("https://www.apexnc.org", "Apex"),
    "fuquayvarina":   ("https://www.fuquay-varina.org", "Fuquay-Varina"),
    "carrboro":       ("https://www.carrboronc.gov", "Carrboro"),
    "durhamdpr":      ("https://www.dprplaymore.org", "Durham"),
}


def _civic(name):
    base, city = CIVICPLUS_SITES[name]
    return lambda: scrape_civicplus(name, base, city)


SOURCES = {
    "stufftodoinrdu": scrape_stufftodoinrdu,
    "kidsoutandabout": scrape_kidsoutandabout,
    "triangleonthecheap": scrape_triangleonthecheap,
    "raleighparent": scrape_raleighparent,
    "wakegov": scrape_wakegov,
    "marbles": lambda: scrape_tec("marbles", "https://www.marbleskidsmuseum.org"),
    "morehead": lambda: scrape_tec("morehead", "https://moreheadplanetarium.org"),
    "fun4raleighkids": scrape_fun4raleighkids,
    **{name: _civic(name) for name in CIVICPLUS_SITES},
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
