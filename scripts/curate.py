#!/usr/bin/env python3
"""Deterministic curator: data/raw_events.json -> data/events.json.

FAMILY-FRIENDLY FILTERING:
This script filters events to show only those appropriate for families with
young children (ages 4-8). It excludes:
- Adult-only events (21+, bars, breweries, nightlife, wine tastings)
- Academic/campus events (lectures, seminars, thesis defenses, department events)
- Business events (networking, board meetings, professional development)
- Scary/horror events (haunted houses, terror-themed)

The filter works in two passes:
1. Hard exclusion: Events matching adult/academic keywords are removed entirely
2. Scoring: Remaining events are scored based on kid-friendliness signals

NOTE: This script ONLY writes to data/events.json. It does NOT touch
data/woodcreek_events.json, which is hand-edited for HOA community events.

Usage:  python scripts/curate.py
"""

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw_events.json"
OUT = ROOT / "data" / "events.json"

NEAR_TOWNS = {"holly springs", "apex", "cary", "fuquay-varina", "morrisville",
              "new hill", "raleigh", "durham", "knightdale", "wake forest", "garner"}
CORE_TOWNS = {"holly springs", "apex", "cary", "fuquay-varina", "morrisville",
              "new hill", "wake forest", "knightdale", "garner"}
FAR_TOWNS = {"sanford", "clayton", "youngsville", "wendell", "pittsboro", "hillsborough",
             "chapel hill", "carrboro", "rolesville"}

# ============================================================================
# FAMILY-FRIENDLY FILTERING
# Events matching these patterns are EXCLUDED entirely (not just scored down)
# ============================================================================

EXCLUDE_ADULT = {
    # Alcohol/nightlife
    "21+", "21 and over", "ages 21", "must be 21", "bar", "brewery", "brewpub",
    "wine tasting", "beer tasting", "cocktail", "happy hour", "nightclub",
    "nightlife", "pub crawl", "wine pairing", "spirits", "sommelier",
    # Dating/singles
    "speed dating", "singles", "singles night", "date night adults only",
    # Adult entertainment
    "burlesque", "cabaret", "adult comedy", "r-rated", "mature audiences",
}

EXCLUDE_ACADEMIC = {
    # Lectures and academic
    "lecture", "seminar", "symposium", "colloquium", "dissertation", "thesis defense",
    "faculty meeting", "department meeting", "academic", "research presentation",
    "scholarly", "peer review", "journal club", "graduate seminar",
    # University-specific
    "alumni event", "alumni networking", "homecoming (adults)", "fraternity",
    "sorority", "student government", "faculty senate", "provost", "dean's",
    "commencement committee", "curriculum committee", "tenure",
}

EXCLUDE_BUSINESS = {
    # Professional/business
    "board meeting", "council meeting", "commission meeting", "committee meeting",
    "business networking", "chamber of commerce", "rotary club", "professional development",
    "career fair", "job fair", "recruitment event", "investor", "shareholders",
    "quarterly meeting", "annual meeting", "strategic planning", "budget hearing",
    "public hearing", "zoning", "planning commission", "city council",
    "arts commission", "parks commission", "advisory board", "town council",
}

EXCLUDE_PATTERNS = [
    r"\b21\+\b", r"\bages?\s*21\s*(?:and\s*)?(?:over|up)\b",
    r"\bgraduate\s+(?:student|seminar|lecture)\b",
    r"\bphd\s+(?:defense|dissertation)\b",
    r"\bfaculty\s+(?:meeting|senate|lunch)\b",
    r"\bdepartment(?:al)?\s+(?:meeting|seminar|colloquium)\b",
    r"\bboard\s+(?:of\s+)?(?:directors|trustees|commissioners)\b",
    r"\bpublic\s+hearing\b", r"\bzoning\s+(?:board|hearing)\b",
    r"\bclosed\b", r"\bclosure\b",
    r"\bsolid waste\b", r"\bwaste (?:collection|schedule|pickup)\b",
    r"\btrash (?:collection|schedule|pickup)\b", r"\brecycling (?:collection|schedule|pickup)\b",
    r"\bschedule delayed\b", r"\bholiday observed\b", r"\bno (?:trash|garbage|collection)\b",
]

# Keywords that boost family-friendliness score
KID_KEYWORDS = {
    "family": 8, "kid": 8, "children": 8, "storytime": 10, "story time": 10,
    "pumpkin": 6, "halloween": 5, "trick-or-treat": 8, "trunk-or-treat": 8,
    "train": 7, "farm": 6, "animal": 7, "corn maze": 7, "festival": 5,
    "museum": 5, "movie": 4, "dance": 4, "craft": 6, "scarecrow": 7,
    "toddler": 8, "preschool": 8, "baby": 5, "sensory": 7, "lego": 7,
    "puppet": 7, "young children": 10, "all ages": 6, "family-friendly": 10,
    "market": 3, "fair": 6, "maze": 6, "skate": 5, "playground": 7,
    "santa": 8, "easter": 7, "egg hunt": 8, "holiday": 5, "christmas": 6,
    "parade": 6, "fireworks": 6, "picnic": 5, "nature": 5, "hike": 4,
    "zoo": 8, "aquarium": 8, "planetarium": 8, "science": 6, "dinosaur": 7,
}

# Keywords that reduce score (but don't exclude)
ADULT_SCORE_PENALTY = {
    "wine", "beer", "brew", "tasting", "open mic", "dj", "nightlife",
    "lindy", "improv", "stand-up", "standup", "metal", "disco", "yoga",
    "trivia", "comedy",  # comedy can be family or adult
}

SCARY_KEYWORDS = {"haunt", "haunted", "fear", "panic", "terror", "scream", "horror"}

DAY_NAMES = {
    "fri": ("fri", "friday"), "sat": ("sat", "saturday"), "sun": ("sun", "sunday"),
}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower())


def is_family_appropriate(e):
    """Return True if event passes family-friendly filter, False to exclude."""
    text = norm(" ".join([
        e.get("title", ""),
        e.get("venue", ""),
        " ".join(e.get("tags", [])),
        e.get("description", ""),
    ]))
    
    # Check exclusion keywords
    for kw in EXCLUDE_ADULT | EXCLUDE_ACADEMIC | EXCLUDE_BUSINESS:
        if kw in text:
            return False
    
    # Check exclusion patterns
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, text, re.I):
            return False
    
    return True


def fix_mojibake(t):
    t = re.sub(r"(?<=\w)�(?=\w)", "'", t)
    t = re.sub(r"\s�\s", " – ", t)
    return t.replace("�", " ").strip()


def clean_title(t):
    t = fix_mojibake(t)
    t = re.sub(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+[A-Z][a-z]{2}\s+\d{1,2}(-\d{1,2})?,\s*", "", t)
    t = re.sub(r"^[A-Z][a-z]{2}\s+\d{1,2}(-\d{1,2})?,\s*", "", t)
    t = re.sub(r"^\d{1,2}:\d{2}\s*[AP]M(\s*-\s*\d{1,2}:\d{2}\s*[AP]M)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*\d+(\.\d+)?\s*mi away.*$", "", t, flags=re.I)
    t = re.split(r"\s[•�]\s", t)[0]
    return re.sub(r"\s+", " ", t).strip(" -–•")


MONTHS = {m: i + 1 for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split())}


def weekend_day_map(raw):
    wk = raw.get("weekend", {})
    try:
        fri, sun = date.fromisoformat(wk["fri"]), date.fromisoformat(wk["sun"])
    except Exception:
        return {}
    out = {}
    for key, off in (("fri", 0), ("sat", 1), ("sun", 2)):
        d = fri + timedelta(days=off)
        if d <= sun:
            out[(d.month, d.day)] = key
    return out


def parse_date_hint(hint):
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?", hint or "")
    if not m:
        return []
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return []
    d1, d2 = int(m.group(2)), int(m.group(3) or m.group(2))
    return [(month, d) for d in range(d1, d2 + 1)]


def resolve_dates(hint, start, end):
    """Resolve 'Nov 14' / 'Nov 14-15' to ISO dates inside [start, end]."""
    out = []
    for month, day in parse_date_hint(hint):
        for year in range(start.year - 1, end.year + 2):
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            if start <= d <= end and d not in out:
                out.append(d)
    return sorted(out)


def detect_days(text):
    days = [d for d, names in DAY_NAMES.items() if any(n in text for n in names)]
    return days or ["sat"]


def detect_city(text):
    hay = norm(text)
    best = None
    for t in NEAR_TOWNS | FAR_TOWNS | {"carrboro", "pittsboro"}:
        idx = hay.find(t)
        if idx == -1:
            continue
        if best is None or idx < best[0] or (idx == best[0] and len(t) > len(best[1])):
            best = (idx, t)
    return best[1].title() if best else ""


def title_key(title):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", norm(title))).strip()


TITLE_MATCH_IGNORE = set(
    "jan january feb february mar march apr april may jun june jul july "
    "aug august sep sept september oct october nov november dec december annual".split()
)


def titles_match(a, b):
    if not a or not b or min(len(a), len(b)) < 8:
        return False
    ta, tb = a.split(), b.split()

    def contains(longer, shorter):
        n = len(shorter)
        return any(longer[i:i + n] == shorter for i in range(len(longer) - n + 1))

    if contains(tb, ta):
        shorter, longer = ta, tb
    elif contains(ta, tb):
        shorter, longer = tb, ta
    else:
        return False

    n = len(shorter)
    for i in range(len(longer) - n + 1):
        if longer[i:i + n] == shorter:
            extra = longer[:i] + longer[i + n:]
            break
    else:
        extra = []
    return all(t in TITLE_MATCH_IGNORE for t in extra)


def time_key(value):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)", (value or "").upper())
    if not m:
        return ""
    hour = int(m.group(1)) % 12
    if m.group(3) == "PM":
        hour += 12
    return f"{hour:02d}:{m.group(2)}"


def score(e):
    """Score event for family-friendliness (0-100)."""
    text = norm(" ".join([e.get("title", ""), e.get("venue", ""), " ".join(e.get("tags", []))]))
    s = 45.0
    tags = set()

    if re.search(r"\bfree\b", text) or "free" in norm(e.get("cost", "")):
        s += 12
        tags.add("free")
    if "family-friendly" in e.get("tags", []):
        s += 15

    kid_hits = sum(v for k, v in KID_KEYWORDS.items() if k in text)
    s += min(kid_hits, 30)
    
    if re.search(r"\bhalloween\b|pumpkin|scarecrow|trunk-or-treat|trick-or-treat", text):
        tags.add("halloween")
    if re.search(r"\bchristmas\b|santa|holiday\s+market|tree\s+lighting", text):
        tags.add("holiday")

    venue_text = e.get("venue", "") or ""
    city = norm(e.get("city", "")) or norm(detect_city(venue_text)) or norm(detect_city(text))
    if city in CORE_TOWNS:
        s += 12
    elif city in NEAR_TOWNS:
        s += 8
    elif city in FAR_TOWNS:
        s -= 4

    if any(k in text for k in SCARY_KEYWORDS):
        s -= 22
        tags.add("scary")
    adult_hits = sum(1 for k in ADULT_SCORE_PENALTY if k in text)
    s -= min(adult_hits * 6, 18)

    for tag in ("outdoor", "indoor"):
        if tag in text:
            tags.add(tag)
    return max(0, min(100, round(s))), tags, city.title()


def get_week_key(event_date_str, today):
    """Return week number (0 = this week, 1 = next week, etc.) for quota distribution."""
    if not event_date_str:
        return 0
    try:
        d = date.fromisoformat(event_date_str)
        days_diff = (d - today).days
        return max(0, days_diff // 7)
    except:
        return 0


def distribute_by_week(events, today, max_total=400):
    """Select events with per-week quotas to spread across the 90-day window.
    
    Strategy:
    - Week 0-1 (this week + next): up to 60 events each (most relevant)
    - Week 2-3: up to 40 events each
    - Week 4-7: up to 25 events each
    - Week 8-12: up to 15 events each
    
    Within each week, take highest-scored events first.
    """
    WEEK_QUOTAS = {
        0: 50, 1: 50,  # This week and next
        2: 35, 3: 35,  # 2-3 weeks out
        4: 30, 5: 30, 6: 30, 7: 30,  # Month 2
        8: 25, 9: 25, 10: 25, 11: 25, 12: 25,  # Month 3
    }
    DEFAULT_QUOTA = 20  # For weeks beyond 12
    
    # Group events by week
    by_week = defaultdict(list)
    for e in events:
        week = get_week_key(e.get("date", ""), today)
        by_week[week].append(e)
    
    # Sort each week by score (descending)
    for week in by_week:
        by_week[week].sort(key=lambda x: -x["family_score"])
    
    # Select events respecting quotas
    selected = []
    for week in sorted(by_week.keys()):
        quota = WEEK_QUOTAS.get(week, DEFAULT_QUOTA)
        week_events = by_week[week][:quota]
        selected.extend(week_events)
        if len(selected) >= max_total:
            break
    
    # Sort final list by date, then score
    selected.sort(key=lambda e: (e.get("date", "9999-99-99"), -e["family_score"]))
    return selected[:max_total]


def main():
    if not RAW.exists():
        raise SystemExit("run scripts/fetch_events.py first — no raw_events.json")
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    seen, events = set(), []
    wkmap = weekend_day_map(raw)
    today = date.today()
    range_info = raw.get("range", {})
    try:
        range_start = date.fromisoformat(range_info["start"]) if range_info.get("start") else today
        range_end = date.fromisoformat(range_info["end"]) if range_info.get("end") else today + timedelta(days=90)
    except Exception:
        range_start, range_end = today, today + timedelta(days=90)
    
    excluded_count = 0
    
    for e in raw.get("raw_events", []):
        # FAMILY FILTER: Skip non-family events
        if not is_family_appropriate(e):
            excluded_count += 1
            continue
        
        raw_title = e.get("title", "")
        event_date = e.get("event_date", "")
        
        head = re.search(
            r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*([A-Za-z]{3}\s+\d{1,2}(-\d{1,2})?)",
            raw_title[:70])
        date_hint = e.get("date_hint")
        if not date_hint:
            m2 = head or re.match(
                r"([A-Za-z]{3}\s+\d{1,2}(-\d{1,2})?)", raw_title)
            date_hint = m2.group(2) if head else (m2.group(1) if m2 else None)
        day_hint = e.get("day_hint") or (head.group(1).lower() if head else None)

        title = clean_title(raw_title)
        if len(title) < 5:
            continue

        candidates = []  # (date_obj|None, days[]|None, date_iso)
        event_date = str(event_date or "")[:10]
        if event_date:
            try:
                d0 = date.fromisoformat(event_date)
            except ValueError:
                d0 = None
            if d0 and range_start <= d0 <= range_end and d0.weekday() in (4, 5, 6):
                md = (d0.month, d0.day)
                candidates.append((d0, [wkmap[md]] if md in wkmap else [], d0.isoformat()))
        elif date_hint:
            for d0 in resolve_dates(date_hint, range_start, range_end):
                if d0.weekday() not in (4, 5, 6):
                    continue
                md = (d0.month, d0.day)
                candidates.append((d0, [wkmap[md]] if md in wkmap else [], d0.isoformat()))
            if not candidates:
                continue  # dated listing outside the fetch range
        elif day_hint in ("fri", "sat", "sun"):
            candidates.append((None, [day_hint], ""))
        else:
            candidates.append((None, None, ""))

        text = norm(" ".join([title, e.get("venue", "")]))
        s, tags, city = score(e)

        for _, days, date_iso in candidates:
            day_list = days if days is not None else detect_days(text)
            key = norm(title)[:60] + "|" + (date_iso or ",".join(day_list)) + "|" + norm(e.get("venue", ""))[:40] + "|" + time_key(e.get("time_hint", ""))
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "id": re.sub(r"[^a-z0-9]+", "-", norm(title)).strip("-")[:60],
                "title": title,
                "days": day_list,
                "date": date_iso,
                "start": e.get("time_hint", "") or "See listing",
                "end": e.get("time_end", ""),
                "venue": e.get("venue", ""),
                "city": e.get("city") or city,
                "cost": e.get("cost") or ("Free" if "free" in tags else "See listing"),
                "url": e.get("url", ""),
                "source": e.get("source", ""),
                "indoor": "indoor" in tags,
                "family_score": s,
                "why": "",
                "tags": sorted(tags),
            })

    feed_dates = set()
    wk = raw.get("weekend", {})
    try:
        feed_fri = date.fromisoformat(wk["fri"])
        feed_dates = {(feed_fri + timedelta(days=i)).isoformat() for i in range(3)}
    except Exception:
        feed_dates = set()
    if feed_dates:
        dated_keys = [title_key(e["title"]) for e in events if e.get("date") in feed_dates]
        if dated_keys:
            kept = []
            for e in events:
                if not e.get("date") and any(titles_match(title_key(e["title"]), dk) for dk in dated_keys):
                    continue
                kept.append(e)
            events = kept

    # Apply week-based distribution for extended ranges
    range_info = raw.get("range", {})
    if "days" in range_info.get("mode", ""):
        events = distribute_by_week(events, today, max_total=400)
    else:
        events.sort(key=lambda e: -e["family_score"])
        events = events[:100]
    
    OUT.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weekend": raw.get("weekend", {}),
        "range": raw.get("range", {}),
        "events": events,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Print statistics
    print(f"wrote {OUT} ({len(events)} family-friendly events)")
    print(f"Excluded {excluded_count} non-family events (adult/academic/business)")


if __name__ == "__main__":
    main()
