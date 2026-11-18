#!/usr/bin/env python3
"""Fetch raw event listings from Triangle-area sources -> data/raw_events.json.

Best-effort, tolerant scraping: one broken source never kills the run.
The agent curation step (REFRESH.md) cleans, dedupes, and ranks this output —
this script only needs to produce reasonable candidates.

Usage:  python scripts/fetch_events.py [--days N]
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
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw_events.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TIMEOUT = 20
PARTIAL_SOURCES = set()

FETCH_DAYS = 3  # default, overridden by --days


def upcoming_weekend(today=None):
    """Return (fri, sun) date objects for the coming/current weekend."""
    today = today or date.today()
    days_to_fri = (4 - today.weekday()) % 7
    fri = today + timedelta(days=days_to_fri)
    return fri, fri + timedelta(days=2)


def get_date_range():
    """Return (start_date, end_date) based on FETCH_DAYS."""
    today = date.today()
    if FETCH_DAYS <= 3:
        return upcoming_weekend()
    return today, today + timedelta(days=FETCH_DAYS)


def get(url):
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    if "Browser Isolation" in r.text or "Zscaler" in r.text[:5000]:
        raise RuntimeError("blocked by proxy browser isolation")
    return BeautifulSoup(r.content, "html.parser")


def _date_hint(d):
    return f"{d.strftime('%b')} {d.day}"


def _day_in_range(d, start, end):
    """Check if date d falls within the fetch range."""
    if isinstance(d, datetime):
        d = d.date()
    return start <= d <= end


def _time_key(value):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)", (value or "").upper())
    if not m:
        return ""
    hour = int(m.group(1)) % 12
    if m.group(3) == "PM":
        hour += 12
    return f"{hour:02d}:{m.group(2)}"


# ============================================================================
# Source scrapers - all updated to respect date range when possible
# ============================================================================

def scrape_stufftodoinrdu():
    """Weekend page: event cards grouped under Friday/Saturday/Sunday day bars."""
    events = []
    soup = get("https://stufftodoinrdu.com/")
    daybar_re = re.compile(
        r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,\s*"
        r"(\d{1,2})\s+([A-Za-z]{3})", re.I)
    weekend_days = {"friday": "fri", "saturday": "sat", "sunday": "sun"}
    for h3 in soup.select("h3 a[href*='/events/']"):
        daybar = h3.find_previous("h2", class_="te-daybar")
        m = daybar_re.match(daybar.get_text(" ", strip=True)) if daybar else None
        if not m:
            continue
        day_hint = weekend_days.get(m.group(1).lower(), "")
        if not day_hint:
            continue
        date_hint = f"{m.group(3).capitalize()} {int(m.group(2))}"
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
            "day_hint": day_hint,
            "date_hint": date_hint,
        })
    return events


def scrape_kidsoutandabout():
    """Weekend roundup highlights."""
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
                    "source": "kidsoutandabout", "tags": ["family"],
                })
        if events:
            break
    return events


def scrape_triangleonthecheap():
    """Day tables: event | time | price | location."""
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
            "source": "triangleonthecheap", "tags": ["budget"],
        })
    return events


RP_HEAD = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Z][a-z]{2}\s+\d{1,2}),\s+"
    r"(?:(\d{1,2}:\d{2}\s*[AP]M)(?:\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?\s+)?(.*)$")
DAY_MAP = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
           "fri": "fri", "sat": "sat", "sun": "sun"}


def scrape_raleighparent():
    """Events calendar with date-prefixed links."""
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
            "tags": ["family"],
            "day_hint": DAY_MAP[wday.lower()],
            "date_hint": date_hint,
        })
    return events


def scrape_civicplus(source_name, base, city, months_ahead=3):
    """CivicPlus calendar. Combines the list view with month grids for extended ranges."""
    events = []
    seen_keys = {}
    start_date, end_date = get_date_range()

    def add_event(title, url, venue, time_hint, time_end, tags, day_hint, date_hint, event_date):
        item = {
            "title": title,
            "url": url,
            "venue": venue,
            "time_hint": time_hint,
            "time_end": time_end,
            "cost": "",
            "source": source_name,
            "city": city,
            "tags": tags,
            "day_hint": day_hint,
            "date_hint": date_hint,
            "event_date": event_date,
        }
        key = (re.sub(r"\s+", " ", title.lower()).strip(), event_date or "", _time_key(time_hint))
        if key in seen_keys:
            idx = seen_keys[key]
            old = events[idx]
            generic_venues = {"", "event location"}
            new_venue = (venue or "").strip().lower()
            old_venue = (old.get("venue") or "").strip().lower()
            if (new_venue not in generic_venues and old_venue in generic_venues) or (time_end and not old.get("time_end")):
                events[idx] = item
            return
        seen_keys[key] = len(events)
        events.append(item)

    # List view has cleaner titles when present, but month grids catch events it omits.
    try:
        soup = get(f"{base}/calendar.aspx?view=list")
        items = soup.select(".calendars .calendar ol li")
    except Exception:
        items = []
    for li in items:
        nm = li.select_one('[itemprop="name"]')
        st = li.select_one('[itemprop="startDate"]')
        a = li.select_one("h3 a[href]")
        if not (nm and st and a):
            continue
        title = nm.get_text(" ", strip=True)
        if len(title) < 5:
            continue
        try:
            dt = datetime.fromisoformat(st.get_text(strip=True))
            event_date = dt.date()
        except Exception:
            continue
        if not _day_in_range(event_date, start_date, end_date):
            continue
        day_hint = dt.strftime("%a").lower()[:3]
        date_hint = _date_hint(dt.date())
        time_hint = dt.strftime("%I:%M %p").lstrip("0")
        loc = li.select_one('span[itemprop="location"] [itemprop="name"]')
        group = li.find_parent(class_="calendar")
        gtitle = group.select_one("h2.title").get_text(strip=True) if group and group.select_one("h2.title") else ""
        add_event(
            title,
            urljoin(base, a["href"]),
            loc.get_text(" ", strip=True) if loc else "",
            time_hint,
            "",
            [gtitle] if gtitle else [],
            day_hint,
            date_hint,
            event_date.isoformat(),
        )

    # Month grids cover the full range, including cities whose list view is empty.
    months_to_fetch = set()
    current = start_date.replace(day=1)
    while current <= end_date:
        months_to_fetch.add((current.month, current.year))
        next_month = current.month % 12 + 1
        next_year = current.year + (1 if current.month == 12 else 0)
        current = current.replace(year=next_year, month=next_month)

    failed_months = 0
    for month, year in sorted(months_to_fetch):
        try:
            soup = get(f"{base}/calendar.aspx?month={month}&year={year}")
        except Exception:
            failed_months += 1
            continue
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
            if not _day_in_range(ev, start_date, end_date):
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
            add_event(
                title,
                urljoin(base, a["href"]) if a else base + "/calendar.aspx",
                meta.get("Location", ""),
                tm.group(1) if tm else "",
                te.group(1) if te else "",
                [cat] if cat else [],
                ev.strftime("%a").lower()[:3],
                _date_hint(ev),
                ev.isoformat(),
            )

    if failed_months and (events or failed_months < len(months_to_fetch)):
        PARTIAL_SOURCES.add(source_name)
    if not events and months_to_fetch and failed_months == len(months_to_fetch):
        raise RuntimeError("all calendar months failed")
    return events


def scrape_wakegov(pages=8):
    """wake.gov/events — Drupal responsive-grid cards."""
    events = []
    start_date, end_date = get_date_range()
    for pg in range(pages):
        try:
            soup = get(f"https://www.wake.gov/events?page={pg}")
        except Exception:
            break
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
            event_date = None
            if dm:
                mon = {"january": 1, "february": 2, "march": 3, "april": 4,
                       "may": 5, "june": 6, "july": 7, "august": 8,
                       "september": 9, "october": 10, "november": 11,
                       "december": 12}.get(dm.group(2).lower())
                if mon:
                    event_date = date(int(dm.group(4)), mon, int(dm.group(3)))
                    if not _day_in_range(event_date, start_date, end_date):
                        continue
                    day_hint = event_date.strftime("%a").lower()[:3]
                    date_hint = _date_hint(event_date)
            events.append({
                "title": title, "url": url,
                "venue": "", "time_hint": tm.group(1) if tm else "",
                "time_end": "", "cost": "", "source": "wakegov",
                "tags": [tail] if tail else [],
                "day_hint": day_hint, "date_hint": date_hint,
                "event_date": event_date.isoformat() if event_date else "",
            })
    return events


def scrape_tec(source_name, base, per_page=50):
    """WordPress 'The Events Calendar' REST API — paginates extended date ranges."""
    start_date, end_date = get_date_range()
    raw_events = []
    page = 1
    total_pages = None
    first_exc = None
    while True:
        try:
            r = requests.get(
                f"{base}/wp-json/tribe/events/v1/events",
                params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                        "per_page": per_page, "status": "publish", "page": page},
                headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            batch = r.json().get("events", [])
        except Exception as exc:
            if first_exc is None:
                first_exc = exc
            if raw_events:
                PARTIAL_SOURCES.add(source_name)
            break
        raw_events.extend(batch)
        try:
            header_pages = r.headers.get("X-WP-TotalPages")
            if header_pages:
                total_pages = int(header_pages)
        except (TypeError, ValueError):
            pass
        if len(batch) < per_page or (total_pages is not None and page >= total_pages) or page >= 10:
            break
        page += 1
    if not raw_events and first_exc is not None:
        raise first_exc

    events = []
    for e in raw_events:
        start = e.get("start_date", "")
        end_str = e.get("end_date", "")
        day_hint = date_hint = time_hint = time_end = ""
        event_date = None
        try:
            dt = datetime.fromisoformat(start.replace(" ", "T"))
            event_date = dt.date()
            day_hint = dt.strftime("%a").lower()[:3]
            date_hint = _date_hint(dt.date())
            time_hint = dt.strftime("%I:%M %p").lstrip("0") if (dt.hour or dt.minute) else ""
        except Exception:
            pass
        try:
            dt_end = datetime.fromisoformat(end_str.replace(" ", "T"))
            time_end = dt_end.strftime("%I:%M %p").lstrip("0") if (dt_end.hour or dt_end.minute) else ""
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
            "time_hint": time_hint, "time_end": time_end, "cost": str(cost),
            "source": source_name,
            "city": venue.get("city", "") if isinstance(venue, dict) else "",
            "tags": [t for t in cats if t],
            "day_hint": day_hint, "date_hint": date_hint,
            "event_date": event_date.isoformat() if event_date else "",
        })
    return events


def scrape_fun4raleighkids():
    """fun4raleighkids.com — Joomla JEvents. Fetches each day in range."""
    events = []
    start_date, end_date = get_date_range()
    days_to_fetch = min((end_date - start_date).days + 1, 90)
    
    for i in range(days_to_fetch):
        day = start_date + timedelta(days=i)
        try:
            soup = get(f"https://fun4raleighkids.com/calendar/day.listevents/{day.year}/{day.month}/{day.day}/-")
        except Exception:
            continue
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
                "event_date": day.isoformat(),
            })
    return events


def scrape_raleigh_api():
    """City of Raleigh JSON API — returns all events, filter by date range."""
    events = []
    start_date, end_date = get_date_range()
    try:
        r = requests.get("https://raleighnc.gov/api/events", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return events
    
    for e in data:
        title = e.get("title", "")
        if len(title) < 5:
            continue
        start_str = e.get("start", "")
        event_date = None
        day_hint = date_hint = time_hint = ""
        if start_str:
            try:
                dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                event_date = dt.date()
                if not _day_in_range(event_date, start_date, end_date):
                    continue
                day_hint = event_date.strftime("%a").lower()[:3]
                date_hint = _date_hint(event_date)
                if dt.hour or dt.minute:
                    time_hint = dt.strftime("%I:%M %p").lstrip("0")
            except Exception:
                pass
        
        events.append({
            "title": title,
            "url": e.get("url", ""),
            "venue": "",
            "city": "Raleigh",
            "time_hint": time_hint,
            "time_end": "",
            "cost": "",
            "source": "raleighnc",
            "tags": ["city"],
            "day_hint": day_hint,
            "date_hint": date_hint,
            "event_date": event_date.isoformat() if event_date else "",
        })
    
    return events


# ============================================================================
# Source registry
# ============================================================================

CIVICPLUS_SITES = {
    # Working CivicPlus sites with accessible calendars
    "hollysprings":   ("https://www.hollyspringsnc.us", "Holly Springs"),
    "apex":           ("https://www.apexnc.org", "Apex"),
    "fuquayvarina":   ("https://www.fuquay-varina.org", "Fuquay-Varina"),
    "carrboro":       ("https://www.carrboronc.gov", "Carrboro"),
    "clayton":        ("https://www.townofclaytonnc.org", "Clayton"),
    "orangecounty":   ("https://www.orangecountync.gov", "Orange County"),
    # Blocked by WAF/firewall: wendell, morrisville, garner, knightdale, 
    # wakeforest, chapelhill, hillsborough, durhamdpr
}

TEC_SITES = {
    "marbles": "https://www.marbleskidsmuseum.org",
    "morehead": "https://moreheadplanetarium.org",
    "dukegardens": "https://gardens.duke.edu",
}

# Removed: LOCALIST_SITES (NC State, UNC) - university events not family-focused


def _civic(name):
    base, city = CIVICPLUS_SITES[name]
    return lambda: scrape_civicplus(name, base, city)


def _tec(name):
    base = TEC_SITES[name]
    return lambda: scrape_tec(name, base)


SOURCES = {
    # Family-focused aggregator sites
    "stufftodoinrdu": scrape_stufftodoinrdu,
    "kidsoutandabout": scrape_kidsoutandabout,
    # triangleonthecheap: blocked by Cloudflare (403)
    "raleighparent": scrape_raleighparent,
    "fun4raleighkids": scrape_fun4raleighkids,
    
    # Government / Regional (family events)
    "wakegov": scrape_wakegov,
    "raleighnc": scrape_raleigh_api,
    
    # CivicPlus town calendars (community/family events)
    **{name: _civic(name) for name in CIVICPLUS_SITES},
    
    # Family venues (The Events Calendar)
    **{name: _tec(name) for name in TEC_SITES},
    
    # Removed: NC State/UNC Localist - university/campus events not family-focused
}


def main():
    global FETCH_DAYS
    import argparse
    parser = argparse.ArgumentParser(description="Fetch Triangle area events")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days to fetch (default: 90)")
    args = parser.parse_args()
    FETCH_DAYS = args.days

    today = date.today()
    fri, sun = upcoming_weekend()
    start_date, end_date = get_date_range()
    range_mode = "weekend" if FETCH_DAYS <= 3 else f"{FETCH_DAYS}days"

    PARTIAL_SOURCES.clear()
    collected, failed = [], []
    for name, fn in SOURCES.items():
        try:
            found = fn()
            print(f"{name}: {len(found)} listings")
            collected.extend(found)
        except Exception as exc:
            print(f"{name}: FAILED ({exc})", file=sys.stderr)
            failed.append(name)

    partial = sorted(PARTIAL_SOURCES)
    if partial:
        print(f"partial sources: {', '.join(partial)}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sat = fri + timedelta(days=1)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weekend": {"fri": fri.isoformat(), "sat": sat.isoformat(), "sun": sun.isoformat()},
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat(), "mode": range_mode},
        "failed_sources": failed,
        "partial_sources": partial,
        "raw_events": collected,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Print stats by date range
    from collections import Counter
    date_counts = Counter()
    for e in collected:
        ed = e.get("event_date", "")
        if ed:
            try:
                d = datetime.strptime(ed, "%Y-%m-%d").date()
                if d <= today + timedelta(days=7):
                    date_counts["This week"] += 1
                elif d <= today + timedelta(days=30):
                    date_counts["30 days"] += 1
                elif d <= today + timedelta(days=60):
                    date_counts["60 days"] += 1
                elif d <= today + timedelta(days=90):
                    date_counts["90 days"] += 1
            except:
                pass
    
    print(f"\nwrote {OUT} ({len(collected)} raw listings, {len(failed)} failed sources)")
    print(f"Date distribution: {dict(date_counts)}")


if __name__ == "__main__":
    main()
