#!/usr/bin/env python3
"""
Daily Calendar Intelligence Check — cron job (v2 multi-cal).
Scans all relevant Google Calendars for today + tomorrow, detects conflicts,
flags prep needs, and reports actionable insights.
"""
import os, json, sys, datetime

client_id = os.environ.get('GOOGLE_CALENDAR_CLIENT_ID')
client_secret = os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET')
refresh_token = os.environ.get('GOOGLE_CALENDAR_REFRESH_TOKEN')

if not all([client_id, client_secret, refresh_token]):
    print("ERROR: Google Calendar credentials not configured.")
    sys.exit(1)

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials(
    token=None,
    refresh_token=refresh_token,
    client_id=client_id,
    client_secret=client_secret,
    token_uri="https://oauth2.googleapis.com/token"
)
service = build('calendar', 'v3', credentials=creds)

now = datetime.datetime.now(datetime.timezone.utc)

# Today's range
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
today_end = today_start + datetime.timedelta(days=1)
tomorrow_end = today_end + datetime.timedelta(days=1)

# Calendar IDs to scan
calendars = {
    "primary": "Health (Personal)",
    "qjplc3c6h3og7ktagsa7enqn64@group.calendar.google.com": "Work",
    "family08720576578057318147@group.calendar.google.com": "Family",
    "ljplm4mteuc1pil2nvfpmtdg3o@group.calendar.google.com": "Jon",
    "c5crv2n9stmu1o4lanau36c8r8@group.calendar.google.com": "Jack",
    "qa2in159mtp2r87pn4sls0on9o@group.calendar.google.com": "Joey",
    "4kagkk3ep4phcdnncljfmvtvi0@group.calendar.google.com": "Josh",
    "l5t358a0ccelnofv6eff2f1m38@group.calendar.google.com": "Bills & Finance",
    "741c8105ed07803c9f58ae102747b9e6ad6194a1439f7a69212e7df3fcfafa1e@group.calendar.google.com": "Bet Mitzvah '27",
    "u0k3vpvuust8ktug22hcc0ri54@group.calendar.google.com": "T10",
    "it8dmr1qaat0fj9pk1vicn6ul8@group.calendar.google.com": "Friends & Fun"
}

def format_dt(dt_str):
    if not dt_str:
        return "All day"
    try:
        dt_str_clean = dt_str.replace('Z', '+00:00')
        if '+' not in dt_str_clean and dt_str_clean.count('-') <= 2:
            dt_str_clean += '+00:00'
        dt = datetime.datetime.fromisoformat(dt_str_clean)
        return dt.astimezone().strftime("%I:%M %p").lstrip("0")
    except:
        return dt_str[:10]

def parse_dt_safe(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None

def is_all_day(e):
    return 'date' in e.get('start', {}) and 'dateTime' not in e.get('start', {})

def overlaps(s1, e1, s2, e2):
    return s1 and e1 and s2 and e2 and max(s1, s2) < min(e1, e2)

# Collect all events
today_events = []   # (calendar_name, event)
tomorrow_events = []

for cal_id, cal_name in calendars.items():
    try:
        events = service.events().list(
            calendarId=cal_id,
            timeMin=today_start.isoformat(),
            timeMax=tomorrow_end.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=100
        ).execute()
        items = events.get('items', [])
    except Exception as e:
        print(f"  [SKIP {cal_name}]: {e}", file=sys.stderr)
        continue
    
    for e in items:
        start_str = e['start'].get('dateTime') or e['start'].get('date')
        if not start_str:
            continue
            
        try:
            dt = parse_dt_safe(start_str)
            if dt is None:
                if 'T' not in start_str:
                    dt = datetime.datetime.fromisoformat(start_str).replace(tzinfo=datetime.timezone.utc)
        except:
            continue
        
        event = {
            "calendar": cal_name,
            "summary": e.get('summary', 'Untitled'),
            "start": start_str,
            "end": e['end'].get('dateTime') or e['end'].get('date'),
            "all_day": is_all_day(e),
            "location": e.get('location', ''),
            "description": (e.get('description') or '')[:300]
        }
        
        # Make dt timezone-aware if naive (all-day events)
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        
        if dt and dt < today_end:
                     today_events.append(event)
                elif dt and today_end <= dt < tomorrow_end:
            tomorrow_events.append(event)

# Build report
report = {
    "date": today_start.strftime("%A, %B %d"),
    "today_count": len(today_events),
    "tomorrow_count": len(tomorrow_events),
    "conflicts": [],
    "prep_needed": [],
    "work_events_today": [],
    "personal_events_today": [],
    "work_events_tomorrow": [],
    "personal_events_tomorrow": []
}

# Categorize
for e in today_events:
    category = "work" if e["calendar"] == "Work" else "personal"
    target = "work_events_today" if category == "work" else "personal_events_today"
    report[target].append(e)

for e in tomorrow_events:
    category = "work" if e["calendar"] == "Work" else "personal"
    target = "work_events_tomorrow" if category == "work" else "personal_events_tomorrow"
    report[target].append(e)

# Detect conflicts: overlapping timed events (across all calendars)
timed_today = [e for e in today_events if not e["all_day"]]
for i, e1 in enumerate(timed_today):
    s1 = parse_dt_safe(e1["start"])
    e1e = parse_dt_safe(e1["end"])
    for e2 in timed_today[i+1:]:
        if e1["calendar"] == e2["calendar"]:
            continue  # Same calendar events shouldn't conflict
        s2 = parse_dt_safe(e2["start"])
        e2e = parse_dt_safe(e2["end"])
        if overlaps(s1, e1e, s2, e2e):
            report["conflicts"].append({
                "event1": f"[{e1['calendar']}] {e1['summary']}",
                "event1_time": f"{format_dt(e1['start'])} - {format_dt(e1['end'])}",
                "event2": f"[{e2['calendar']}] {e2['summary']}",
                "event2_time": f"{format_dt(e2['start'])} - {format_dt(e2['end'])}"
            })

# Check prep needs across all events
prep_keywords = ['presentation', 'interview', 'dentist', 'doctor', 'vet', 'oil change',
                 'inspection', 'plumber', 'hvac', 'meeting with', '1:1', 'sprint review',
                 'sprint planning', 'portfolio review', 'performance review']
all_upcoming = today_events + tomorrow_events
for e in all_upcoming:
    title = e["summary"].lower()
    desc = e["description"].lower()
    combined = title + ' ' + desc
    
    matching_kw = [kw for kw in prep_keywords if kw in combined]
    if matching_kw:
        when = "Tomorrow" if e in tomorrow_events else "Today"
        report["prep_needed"].append({
            "calendar": e["calendar"],
            "title": e["summary"],
            "when": when,
            "time": format_dt(e["start"]),
            "keywords": matching_kw
        })

# Output as JSON
print(json.dumps(report, indent=2, default=str))