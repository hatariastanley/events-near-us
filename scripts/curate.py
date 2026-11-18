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
    "family": 4, "kid": 10, "kidz": 10, "children": 10, "storytime": 18, "story time": 18,
    "pumpkin": 8, "halloween": 6, "trick-or-treat": 14, "trunk-or-treat": 14,
    "train": 8, "farm": 8, "animal": 7, "corn maze": 10, "festival": 3,
    "museum": 6, "movie": 4, "dance": 4, "craft": 6, "scarecrow": 8,
    "toddler": 12, "preschool": 12, "baby": 10, "sensory": 12, "lego": 10,
    "puppet": 10, "young children": 15, "all ages": 10, "family-friendly": 8,
    "market": 1, "farmers market": 4, "fair": 3, "maze": 4, "skate": 3, "playground": 10,
    "santa": 10, "easter": 7, "egg hunt": 15, "holiday": 4, "christmas": 5,
    "tree lighting": 8, "parade": 8, "fireworks": 8, "picnic": 5, "nature": 2, "hike": 1,
    "zoo": 14, "aquarium": 14, "planetarium": 14, "science": 7, "dinosaur": 10,
}

PRACTICAL_KEYWORDS = {
    "stroller-friendly": 8, "stroller": 6, "rainy day": 5,
    "quiet": 4, "family restrooms": 6,
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
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", (value or "").upper())
    if not m:
        return ""
    hour = int(m.group(1)) % 12
    if m.group(3) == "PM":
        hour += 12
    return f"{hour:02d}:{m.group(2) or '00'}"


def merge_duplicate_events(events):
    """Merge cross-source duplicates that share date, start time, city, and title."""
    def title_similar(a, b):
        ta, tb = title_key(a), title_key(b)
        if not ta or not tb:
            return False
        if ta == tb:
            return True
        short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        return len(short) >= 12 and short in long

    groups = defaultdict(list)
    for e in events:
        if not e.get("date"):
            continue
        groups[(e["date"], time_key(e.get("start", "")))].append(e)

    merged = []
    for members in groups.values():
        clusters = []
        for e in sorted(members, key=lambda x: (-x["family_score"], len(x["title"]))):
            for cluster in clusters:
                ca = norm(cluster[0].get("city", "")).strip()
                cb = norm(e.get("city", "")).strip()
                if (not ca or not cb or ca == cb) and title_similar(cluster[0]["title"], e["title"]):
                    cluster.append(e)
                    break
            else:
                clusters.append([e])
        for cluster in clusters:
            ordered = sorted(cluster, key=lambda x: (-x["family_score"], len(x["title"]), 0 if x.get("end") else 1, 0 if x.get("venue") else 1))
            primary = ordered[0]
            for donor in ordered[1:]:
                if not primary.get("end") and donor.get("end"):
                    primary["end"] = donor["end"]
                if not primary.get("venue") and donor.get("venue"):
                    primary["venue"] = donor["venue"]
                if (not primary.get("cost") or primary.get("cost") == "See listing") and donor.get("cost"):
                    primary["cost"] = donor["cost"]
                tags = set(primary.get("tags", [])) | set(donor.get("tags", []))
                if tags:
                    primary["tags"] = sorted(tags)
            merged.append(primary)
    merged.extend(e for e in events if not e.get("date"))
    return merged


def keyword_hits(text, mapping):
    total = 0
    for k, v in mapping.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"s?(?![a-z0-9])", text):
            total += v
    return total


def score(e):
    """Score event for family-friendliness (0-100)."""
    text = norm(" ".join([e.get("title", ""), e.get("venue", ""), " ".join(e.get("tags", []))]))
    text = text.replace("’", "").replace("'", "")
    s = 45.0
    tags = set()
    tag_set = {norm(t) for t in e.get("tags", [])}

    if re.search(r"\bfree\b", text) or "free" in norm(e.get("cost", "")):
        s += 12
        tags.add("free")
    if "family-friendly" in tag_set or "family" in tag_set:
        s += 12

    kid_hits = keyword_hits(text, KID_KEYWORDS)
    s += min(kid_hits, 36)
    practical_hits = keyword_hits(text, PRACTICAL_KEYWORDS)
    s += min(practical_hits, 12)
    if "indoor" in text:
        s += 4
    elif "outdoor" in text:
        s += 2
    
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
    
    def occurrence_key(e):
        when = e.get("date") or ",".join(e.get("days") or [])
        return (norm(e.get("title", ""))[:80], when)

    # Group events by week
    by_week = defaultdict(list)
    for e in events:
        week = get_week_key(e.get("date", ""), today)
        by_week[week].append(e)

    # Select event occurrences respecting quotas; keep every session in a chosen occurrence.
    selected = []
    for week in sorted(by_week.keys()):
        quota = WEEK_QUOTAS.get(week, DEFAULT_QUOTA)
        groups = defaultdict(list)
        for e in by_week[week]:
            groups[occurrence_key(e)].append(e)
        ordered = sorted(groups.values(), key=lambda g: -max(x["family_score"] for x in g))
        week_groups = 0
        for group in ordered:
            if week_groups >= quota:
                break
            if len(selected) + len(group) > max_total:
                continue
            selected.extend(group)
            week_groups += 1
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

    events = merge_duplicate_events(events)

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
