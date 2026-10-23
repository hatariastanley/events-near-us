#!/usr/bin/env python3
"""Deterministic curator: data/raw_events.json -> data/events.json.

Applies the mechanical parts of the family-fit rubric (requirements doc):
kid-keyword appeal, whole-family signals, cost, ease, and proximity to the
Holly Springs / Apex / Cary core. This is the automatic baseline — the
LLM pass in REFRESH.md produces higher-quality `why` text and day accuracy
and should overwrite this output when it runs.

Usage:  python scripts/curate.py
"""

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw_events.json"
OUT = ROOT / "data" / "events.json"

NEAR_TOWNS = {"holly springs", "apex", "cary", "fuquay-varina", "morrisville",
              "new hill", "raleigh", "durham", "knightdale", "wake forest", "garner"}
CORE_TOWNS = {"holly springs", "apex", "cary", "fuquay-varina", "morrisville", "new hill"}
FAR_TOWNS = {"sanford", "clayton", "youngsville", "wendell", "pittsboro", "hillsborough",
             "chapel hill", "carrboro"}

KID_KEYWORDS = {
    "family": 8, "kid": 8, "children": 8, "storytime": 8, "story time": 8,
    "pumpkin": 6, "halloween": 5, "trick-or-treat": 7, "trunk-or-treat": 7,
    "train": 7, "farm": 6, "animal": 6, "corn maze": 7, "festival": 5,
    "museum": 5, "movie": 4, "dance": 4, "craft": 5, "scarecrow": 7,
    "market": 3, "fair": 6, "maze": 6, "skate": 5, "movie": 4, "encanto": 6,
    "moana": 6, "star wars": 5, "dog": 4, "pup": 4, "nature": 4, "hike": 4,
}
ADULT_KEYWORDS = {"21+", "bar", "trivia", "comedy", "speed dating", "singles",
                  "wine", "beer", "brew", "tasting", "open mic", "dj", "nightlife",
                  "lindy", "improv", "stand-up", "standup", "metal", "disco", "yoga"}
SCARY_KEYWORDS = {"haunt", "haunted", "fear", "panic", "terror", "scream"}
DAY_NAMES = {
    "fri": ("fri", "friday"), "sat": ("sat", "saturday"), "sun": ("sun", "sunday"),
}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower())


def detect_days(text):
    days = [d for d, names in DAY_NAMES.items() if any(n in text for n in names)]
    return days or ["sat"]  # weekend listings without a day default to Saturday


def detect_city(text):
    towns = NEAR_TOWNS | FAR_TOWNS | {"carrboro", "pittsboro"}
    for t in towns:
        if t in text:
            return t.title()
    return ""


def score(e):
    text = norm(" ".join([e.get("title", ""), e.get("venue", ""), " ".join(e.get("tags", []))]))
    s = 45.0
    tags = set()

    if re.search(r"\bfree\b", text) or "free" in norm(e.get("cost", "")):
        s += 12
        tags.add("free")
    if "family-friendly" in e.get("tags", []):
        s += 15

    kid_hits = sum(v for k, v in KID_KEYWORDS.items() if k in text)
    s += min(kid_hits, 25)
    if re.search(r"\bhalloween\b|pumpkin|scarecrow|trunk-or-treat|trick-or-treat", text):
        tags.add("halloween")

    city = norm(e.get("city", "")) or norm(detect_city(text))
    if city in CORE_TOWNS:
        s += 12
    elif city in NEAR_TOWNS:
        s += 8
    elif city in FAR_TOWNS:
        s -= 4

    if any(k in text for k in SCARY_KEYWORDS):
        s -= 22
        tags.add("scary")
    adult_hits = sum(1 for k in ADULT_KEYWORDS if k in text)
    s -= min(adult_hits * 8, 24)

    for tag in ("outdoor", "indoor"):
        if tag in text:
            tags.add(tag)
    return max(0, min(100, round(s))), tags, city.title()


def main():
    if not RAW.exists():
        raise SystemExit("run scripts/fetch_events.py first — no raw_events.json")
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    seen, events = set(), []

    for e in raw.get("raw_events", []):
        title = re.sub(r"\s+", " ", e.get("title", "")).strip()
        if len(title) < 5:
            continue
        key = norm(title)[:60]
        if key in seen:
            continue
        seen.add(key)

        text = norm(" ".join([title, e.get("venue", "")]))
        s, tags, city = score(e)
        events.append({
            "id": re.sub(r"[^a-z0-9]+", "-", norm(title)).strip("-")[:60],
            "title": title,
            "days": detect_days(text),
            "start": e.get("time_hint", "") or "See listing",
            "end": "",
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

    events.sort(key=lambda e: e["family_score"], reverse=True)
    events = events[:40]
    OUT.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weekend": raw.get("weekend", {}),
        "events": events,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(events)} events)")


if __name__ == "__main__":
    main()
