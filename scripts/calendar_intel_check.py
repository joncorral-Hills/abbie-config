#!/usr/bin/env python3
"""
Daily Calendar Intelligence Check — cron job.
Reads today's Google Calendar events, detects conflicts,
identifies prep needs, and reports changes since yesterday.
"""
import os, json, datetime, sys

client_id = os.environ.get('GOOGLE_CALENDAR_CLIENT_ID')
client_secret = os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET')
refresh_token = os.environ.get('GOOGLE_CALENDAR_REFRESH_TOKEN')

if not all([client_id, client_secret, refresh_token]):
    print("ERROR: Google Calendar credentials not configured.")
    sys.exit(1)

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def get_service():
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build('calendar', 'v3', credentials=creds)

def get_tz():
    """Determine CT offset. CDT through Nov 1 2026, then CST."""
    now = datetime.datetime.now(datetime.timezone.utc)
    # DST ends Nov 1 2026 (first Sunday of Nov)
    dst_end = datetime.datetime(2026, 11, 1, 7, 0, tzinfo=datetime.timezone.utc)  # 2am CT = 7am UTC
    if now < dst_end:
        return -5  # CDT
    return -6  # CST

tz_offset = get_tz()
tz_sign = "-" if tz_offset < 0 else "+"
tz_abs = abs(tz_offset)
tz_str = f"{tz_sign}{tz_abs:02d}:00"

def format_dt(dt_str):
    """Format ISO datetime to readable time."""
    if not dt_str:
        return "All day"
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        ct = dt.astimezone()
        return ct.strftime("%I:%M %p").lstrip("0")
    except:
        return dt_str[:10]

def is_all_day(event):
    """Check if event is all-day."""
    start = event.get('start', {})
    return 'date' in start and 'dateTime' not in start

def overlap(e1_start, e1_end, e2_start, e2_end):
    """Check if two time ranges overlap."""
    return max(e1_start, e2_start) < min(e1_end, e2_end)

def parse_dt(dt_str):
    """Parse ISO datetime to sortable."""
    if not dt_str:
        return None
    return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))

try:
    service = get_service()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Today's range in UTC
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)
    
    # Also get tomorrow for early-morning events
    tomorrow_start = today_end
    tomorrow_end = tomorrow_start + datetime.timedelta(days=1)
    
    start_str = today_start.isoformat()
    end_str = tomorrow_end.isoformat()
    
    print(f"Fetching events from {start_str} to {end_str}", file=sys.stderr)
    
    # Fetch today + tomorrow
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_str,
        timeMax=end_str,
        singleEvents=True,
        orderBy='startTime',
        maxResults=50
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        print("NO_EVENTS")
        sys.exit(0)
    
    # Separate today and tomorrow
    today_events = []
    tomorrow_events = []
    
    for e in events:
        start_dt = e['start'].get('dateTime') or e['start'].get('date')
        if not start_dt:
            continue
        
        try:
            if 'T' in start_dt:
                e_dt = datetime.datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
            else:
                e_dt = datetime.datetime.fromisoformat(start_dt)
                e_dt = e_dt.replace(tzinfo=datetime.timezone.utc) if e_dt.tzinfo is None else e_dt
        except:
            continue
        
        if today_start <= e_dt < tomorrow_start:
            today_events.append(e)
        elif tomorrow_start <= e_dt < tomorrow_end:
            tomorrow_events.append(e)
    
    # Output structured data
    report = {
        "date": today_start.strftime("%A, %B %d, %Y"),
        "today_count": len(today_events),
        "tomorrow_count": len(tomorrow_events),
        "conflicts": [],
        "prep_needed": [],
        "today_events": [],
        "tomorrow_events": []
    }
    
    # Process today's events
    timed_events = [e for e in today_events if not is_all_day(e)]
    all_day_events = [e for e in today_events if is_all_day(e)]
    
    # Check for overlaps among timed events
    timed_sorted = sorted(timed_events, key=lambda e: e['start'].get('dateTime', ''))
    
    for e in timed_sorted:
        s = e['start'].get('dateTime', '')
        en = e['end'].get('dateTime', '')
        report["today_events"].append({
            "title": e.get('summary', 'Untitled'),
            "start": format_dt(s),
            "end": format_dt(en),
            "all_day": False,
            "location": e.get('location', ''),
            "description": (e.get('description', '') or '')[:200]
        })
    
    for e in all_day_events:
        report["today_events"].append({
            "title": e.get('summary', 'Untitled'),
            "start": "All day",
            "end": "All day",
            "all_day": True
        })
    
    # Detect conflicts (overlapping timed events)
    for i, e1 in enumerate(timed_sorted):
        for e2 in timed_sorted[i+1:]:
            s1 = parse_dt(e1['start'].get('dateTime', ''))
            e1_end = parse_dt(e1['end'].get('dateTime', ''))
            s2 = parse_dt(e2['start'].get('dateTime', ''))
            e2_end = parse_dt(e2['end'].get('dateTime', ''))
            
            if s1 and e1_end and s2 and e2_end and overlap(s1, e1_end, s2, e2_end):
                report["conflicts"].append({
                    "event1": e1.get('summary', 'Untitled'),
                    "event1_time": f"{format_dt(e1['start'].get('dateTime',''))} - {format_dt(e1['end'].get('dateTime',''))}",
                    "event2": e2.get('summary', 'Untitled'),
                    "event2_time": f"{format_dt(e2['start'].get('dateTime',''))} - {format_dt(e2['end'].get('dateTime',''))}"
                })
    
    # Check for prep-required events across today+tomorrow
    all_upcoming = today_events + tomorrow_events
    prep_keywords = ['dentist', 'doctor', 'appointment', 'meeting', 'interview', 
                     'presentation', 'review', '1:1', 'standup', 'sprint', 'vet',
                     'oil change', 'inspection', 'plumber', 'hvac']
    
    for e in all_upcoming:
        title = e.get('summary', '').lower()
        desc = (e.get('description', '') or '').lower()
        combined = title + ' ' + desc
        
        # Check for prep triggers
        prep_reasons = []
        for kw in prep_keywords:
            if kw in combined:
                prep_reasons.append(kw)
        
        if prep_reasons:
            # Determine if this is today or tomorrow
            s = e['start'].get('dateTime') or e['start'].get('date')
            is_tomorrow_event = False
            try:
                if 'T' in s:
                    e_dt = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
                else:
                    e_dt = datetime.datetime.fromisoformat(s)
                    e_dt = e_dt.replace(tzinfo=datetime.timezone.utc) if e_dt.tzinfo is None else e_dt
                is_tomorrow_event = tomorrow_start <= e_dt < tomorrow_end
            except:
                pass
            
            when = "Tomorrow" if is_tomorrow_event else "Today"
            report["prep_needed"].append({
                "title": title,
                "when_who": when,
                "time": format_dt(e['start'].get('dateTime') or e['start'].get('date')),
                "reasons": list(set(prep_reasons))
            })
    
    print(json.dumps(report, indent=2))

except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)