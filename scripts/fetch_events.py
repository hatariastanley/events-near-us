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


# ============================================================================
# Source scrapers - all updated to respect date range when possible
# ============================================================================

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
            "day_hint": "",
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
    """CivicPlus month-grid calendar. Fetches multiple months for extended ranges."""
    events = []
    start_date, end_date = get_date_range()
    
    # Try list view first
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
            event_date = None
            if st:
                try:
                    dt = datetime.fromisoformat(st.get_text(strip=True))
                    event_date = dt.date()
                    if not _day_in_range(event_date, start_date, end_date):
                        continue
                    day_hint = dt.strftime("%a").lower()[:3]
                    date_hint = _date_hint(dt.date())
                    time_hint = dt.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    pass
            loc = li.select_one('span[itemprop="location"] [itemprop="name"]')
            group = li.find_parent(class_="calendar")
            gtitle = group.select_one("h2.title").get_text(strip=True) if group and group.select_one("h2.title") else ""
            events.append({
                "title": title,
                "url": urljoin(base, a["href"]),
                "venue": loc.get_text(" ", strip=True) if loc else "",
                "time_hint": time_hint, "time_end": "",
                "cost": "", "source": source_name, "city": city,
                "tags": [gtitle] if gtitle else [],
                "day_hint": day_hint, "date_hint": date_hint,
                "event_date": event_date.isoformat() if event_date else "",
            })
        if events:
            return events
    
    # Fallback to month grid - fetch multiple months for extended ranges
    months_to_fetch = set()
    current = start_date.replace(day=1)
    while current <= end_date:
        months_to_fetch.add((current.month, current.year))
        next_month = current.month % 12 + 1
        next_year = current.year + (1 if current.month == 12 else 0)
        current = current.replace(year=next_year, month=next_month)
    
    for month, year in months_to_fetch:
        try:
            soup = get(f"{base}/calendar.aspx?month={month}&year={year}")
        except Exception:
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
                "event_date": ev.isoformat(),
            })
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


def scrape_tec(source_name, base, per_page=100):
    """WordPress 'The Events Calendar' REST API — supports extended date ranges."""
    start_date, end_date = get_date_range()
    r = requests.get(
        f"{base}/wp-json/tribe/events/v1/events",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                "per_page": per_page, "status": "publish"},
        headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    events = []
    for e in r.json().get("events", []):
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


def scrape_localist(source_name, base, city="", per_page=100):
    """Localist API (NC State, UNC, etc.) — supports extended date ranges."""
    start_date, end_date = get_date_range()
    days = (end_date - start_date).days
    events = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"{base}/api/2/events",
                params={"page": page, "pp": per_page, "days": days},
                headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        
        event_list = data.get("events", [])
        if not event_list:
            break
        
        for item in event_list:
            e = item.get("event", {})
            title = e.get("title", "")
            if len(title) < 5:
                continue
            first_date = e.get("first_date", "")
            event_date = None
            day_hint = date_hint = ""
            if first_date:
                try:
                    event_date = datetime.strptime(first_date, "%Y-%m-%d").date()
                    if not _day_in_range(event_date, start_date, end_date):
                        continue
                    day_hint = event_date.strftime("%a").lower()[:3]
                    date_hint = _date_hint(event_date)
                except Exception:
                    pass
            
            location = e.get("location_name", "") or e.get("location", "")
            address = e.get("address", "")
            cost = e.get("ticket_cost", "") or ("Free" if e.get("free") else "")
            tags = e.get("tags", []) or []
            
            events.append({
                "title": title,
                "url": f"{base}/event/{e.get('urlname', e.get('id', ''))}",
                "venue": location,
                "city": city,
                "time_hint": "",
                "time_end": "",
                "cost": str(cost)[:60],
                "source": source_name,
                "tags": tags[:5],
                "day_hint": day_hint,
                "date_hint": date_hint,
                "event_date": event_date.isoformat() if event_date else "",
            })
        
        page += 1
        if page > 5:  # Limit pages
            break
    
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

LOCALIST_SITES = {
    "ncstate": ("https://calendar.ncsu.edu", "Raleigh"),
    "unc": ("https://calendar.unc.edu", "Chapel Hill"),
}


def _civic(name):
    base, city = CIVICPLUS_SITES[name]
    return lambda: scrape_civicplus(name, base, city)


def _tec(name):
    base = TEC_SITES[name]
    return lambda: scrape_tec(name, base)


def _localist(name):
    base, city = LOCALIST_SITES[name]
    return lambda: scrape_localist(name, base, city)


SOURCES = {
    # Aggregator sites
    "stufftodoinrdu": scrape_stufftodoinrdu,
    "kidsoutandabout": scrape_kidsoutandabout,
    # triangleonthecheap: blocked by Cloudflare (403)
    "raleighparent": scrape_raleighparent,
    "fun4raleighkids": scrape_fun4raleighkids,
    
    # Government / Regional
    "wakegov": scrape_wakegov,
    "raleighnc": scrape_raleigh_api,
    
    # CivicPlus town calendars
    **{name: _civic(name) for name in CIVICPLUS_SITES},
    
    # The Events Calendar (WordPress) sites
    **{name: _tec(name) for name in TEC_SITES},
    
    # Localist university calendars
    **{name: _localist(name) for name in LOCALIST_SITES},
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
    sat = fri + timedelta(days=1)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weekend": {"fri": fri.isoformat(), "sat": sat.isoformat(), "sun": sun.isoformat()},
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat(), "mode": range_mode},
        "failed_sources": failed,
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
