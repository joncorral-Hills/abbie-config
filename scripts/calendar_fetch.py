#!/usr/bin/env python3
"""Fetch and parse Google Calendar ICS feeds."""
import json, sys, re, urllib.request
from datetime import datetime, timedelta, timezone

CONFIG = "/home/ubuntu/.hermes/config/calendars.json"

# Parse ICS VEVENT blocks
def parse_ics(text):
    events = []
    # Unfold continuation lines
    text = re.sub(r"\r?\n ", "", text)
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.DOTALL):
        ev = {}
        for line in block.strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                ev[key] = val
        events.append(ev)
    return events

def parse_dt(s):
    """Parse DTSTART/DTEND values like 20270123T143000Z or 20251007."""
    s = s.strip()
    if "T" in s:
        s = s.rstrip("Z")
        return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)

def fetch_cal(name, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse_ics(r.read().decode("utf-8", errors="ignore"))

def upcoming(events, days=14):
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    out = []
    for ev in events:
        try:
            start = parse_dt(ev.get("DTSTART", ""))
            if now <= start <= cutoff:
                out.append({
                    "summary": ev.get("SUMMARY", "Untitled"),
                    "start": start,
                    "end": parse_dt(ev.get("DTEND", ev.get("DTSTART", ""))),
                    "location": ev.get("LOCATION", "").replace("\\,", ","),
                    "description": re.sub(r"<[^>]+>", "", ev.get("DESCRIPTION", "")).strip(),
                })
        except Exception:
            continue
    out.sort(key=lambda x: x["start"])
    return out

def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    with open(CONFIG) as f:
        cfg = json.load(f)

    for cal in cfg["calendars"]:
        print(f"\n## {cal['name']}")
        try:
            events = fetch_cal(cal["name"], cal["url"])
            hits = upcoming(events, days)
            if not hits:
                print("  No upcoming events.")
                continue
            for ev in hits:
                local = ev["start"].astimezone()
                date_str = local.strftime("%a %b %d")
                time_str = local.strftime("%I:%M %p").lstrip("0")
                loc = f" — {ev['location']}" if ev["location"] else ""
                print(f"  {date_str} @ {time_str}: {ev['summary']}{loc}")
                if ev["description"]:
                    print(f"    {ev['description'][:100]}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    main()
