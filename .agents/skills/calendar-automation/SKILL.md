---
name: calendar-automation
description: >
  Google Calendar integration for smart event scheduling and conflict detection. Auto-books health appointments, financial review reminders, home maintenance tasks, and tax deadlines into Google Calendar. Cross-references work calendar (from Alfred handoff) with personal appointments to detect scheduling conflicts. Provides daily morning agenda briefings via Telegram.
requires:
  bins: [python3]
  pip: [google-auth, google-auth-oauthlib, google-api-python-client]
  env: [NOTION_API_KEY, GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_REFRESH_TOKEN]
---

# Calendar Automation

## Overview

The `calendar-automation` skill acts as Allie's centralized scheduling engine. It ingests tasks, deadlines, and appointments from various internal skills (health, finance, tax, home maintenance) and intelligently schedules them onto Jon's Google Calendar. It ensures personal appointments do not conflict with his work schedule (provided via Alfred handoff) and delivers daily consolidated briefings.

```text
+-------------------+     +--------------------+     +-------------------+
|  health-planner   |     | financial-planner  |     |   tax-planner     |
| (Family Health DB)|     | (Bills/Activation) |     |  (Tax Deadlines)  |
+---------+---------+     +---------+----------+     +---------+---------+
          |                         |                          |
          v                         v                          v
+------------------------------------------------------------------------+
|                                                                        |
|                      calendar-automation (Allie)                       |
|                                                                        |
|  [ Module A: Smart Scheduling ]      [ Module B: Conflict Detection ]  |
|                                                                        |
+---------+---------------------------------+------------------+---------+
          |                                 ^                  |
          | Read Context                    | Read Work Cal    | Write Events
          v                                 |                  v
+-------------------+             +---------+----------+ +-------------------+
| home-maintenance  |             | Alfred Handoff DB  | | Google Calendar   |
| (Seasonal/Vendors)|             | (Work Schedule)    | | (Personal Cal)    |
+-------------------+             +--------------------+ +-------------------+
```

## Setup (One-Time)

### Google Cloud & OAuth Credentials
This skill requires direct integration with the Google Calendar API.

1. **Create Google Cloud Project**: Jon creates a new project in the Google Cloud Console.
2. **Enable API**: Enable the "Google Calendar API" for the project.
3. **Configure OAuth Consent Screen**: Set up an internal or test app with the scope `https://www.googleapis.com/auth/calendar.events`.
4. **Create Credentials**: Create OAuth 2.0 Client ID credentials (Desktop app type).
5. **Download Credentials**: Save the client ID and client secret.
6. **Authorization Flow**: Run the OAuth flow to generate a `GOOGLE_CALENDAR_REFRESH_TOKEN`.

### OAuth Flow Pseudocode

```python
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def run_oauth_flow(client_id: str, client_secret: str) -> str:
    """
    Executes the OAuth flow to obtain a refresh token.
    Run this manually via the CLI or Telegram interface setup step.
    """
    client_config = {
        "installed": {
            "client_id": client_id,
            "project_id": "allie-calendar",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    # Output the refresh token to be saved in env variables
    print("Add this to your environment variables:")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={creds.refresh_token}")
    
    return creds.refresh_token
```

## Modules

### Module A: Smart Scheduling

**Purpose:** Intelligently book events, reminders, and appointments into Google Calendar from various Notion databases while avoiding conflicts.

**Event Sources and Booking Rules:**

| Source Skill | Event Type | Calendar | Default Reminder | Booking Logic |
|-------------|------------|----------|-------------------|---------------|
| `health-planner` | Family Health Calendar items with Status=Due or Overdue | Personal | 1 day + 1 hour | Suggest 3 time slots, book on confirmation |
| `financial-planner` | Freedom Flex quarterly activation | Personal | 3 days before | Book as all-day reminder |
| `tax-planner` | Quarterly estimated tax deadlines | Personal | 1 week + 1 day | Book as all-day event |
| `home-maintenance` | Seasonal prep checklist | Personal | 1 week before | Book as all-day event on season start |
| `home-maintenance` | Vendor appointments | Personal | 1 day + 1 hour | Book at specific time |
| `project-board` | Tasks with due dates | Personal | 1 day before | Book as all-day reminder |

**Booking Protocol:**
1. Check for conflicts in the target time window using the Google Calendar API `freebusy` query.
2. If conflict → suggest 3 alternative slots (next available morning 9-11, afternoon 1-4, or weekend).
3. If no conflict → book directly, confirm via Telegram.
4. All auto-booked events tagged with `[Allie]` prefix.
5. Include event description with source skill context.

**Algorithm Pseudocode:**

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime

def get_calendar_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ['GOOGLE_CALENDAR_REFRESH_TOKEN'],
        client_id=os.environ['GOOGLE_CALENDAR_CLIENT_ID'],
        client_secret=os.environ['GOOGLE_CALENDAR_CLIENT_SECRET'],
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build('calendar', 'v3', credentials=creds)

def check_freebusy(service, start_time: str, end_time: str) -> bool:
    """Checks if the user is busy during the requested time window."""
    body = {
        "timeMin": start_time,
        "timeMax": end_time,
        "items": [{"id": "primary"}]
    }
    events_result = service.freebusy().query(body=body).execute()
    busy_intervals = events_result['calendars']['primary']['busy']
    return len(busy_intervals) > 0

def suggest_alternative_slots(service, preferred_date: datetime.date) -> list:
    """Suggests 3 alternative slots if a conflict is found."""
    slots = []
    current_date = preferred_date
    
    while len(slots) < 3:
        # Check Morning 9-11
        morning_start = f"{current_date}T09:00:00-05:00"
        morning_end = f"{current_date}T11:00:00-05:00"
        if not check_freebusy(service, morning_start, morning_end):
            slots.append(f"{current_date} Morning (9-11)")
            if len(slots) == 3: break
            
        # Check Afternoon 1-4
        afternoon_start = f"{current_date}T13:00:00-05:00"
        afternoon_end = f"{current_date}T16:00:00-05:00"
        if not check_freebusy(service, afternoon_start, afternoon_end):
            slots.append(f"{current_date} Afternoon (1-4)")
            if len(slots) == 3: break
            
        current_date += datetime.timedelta(days=1)
        
    return slots

def book_event(title: str, start: str, end: str, source_context: str, is_all_day: bool = False):
    service = get_calendar_service()
    
    if not is_all_day and check_freebusy(service, start, end):
        pref_date = datetime.datetime.fromisoformat(start).date()
        alternatives = suggest_alternative_slots(service, pref_date)
        return {"status": "conflict", "alternatives": alternatives}
        
    event_body = {
        'summary': f'[Allie] {title}',
        'description': f'Auto-scheduled from: {source_context}',
    }
    
    if is_all_day:
        event_body['start'] = {'date': start.split('T')[0]}
        event_body['end'] = {'date': end.split('T')[0]}
    else:
        event_body['start'] = {'dateTime': start, 'timeZone': 'America/Chicago'}
        event_body['end'] = {'dateTime': end, 'timeZone': 'America/Chicago'}
        
    created_event = service.events().insert(calendarId='primary', body=event_body).execute()
    return {"status": "booked", "event_url": created_event.get('htmlLink')}
```

### Module B: Conflict Detection

**Purpose:** Cross-reference Jon's personal calendar with his work schedule to prevent overlaps and suggest resolutions.

**Data Sources:**
- Personal: Google Calendar API
- Work: `work-context-handoff` Notion DB (or direct Google Calendar if configured)

**Algorithm Pseudocode:**

```python
def detect_overlaps(personal_events: list, work_events: list) -> list:
    """Finds overlapping events between two schedules."""
    conflicts = []
    for p_event in personal_events:
        p_start = p_event['start'].get('dateTime') or p_event['start'].get('date')
        p_end = p_event['end'].get('dateTime') or p_event['end'].get('date')
        
        for w_event in work_events:
            w_start = w_event['start']
            w_end = w_event['end']
            
            # Simple overlap logic (assuming ISO format strings are sortable/comparable)
            if max(p_start, w_start) < min(p_end, w_end):
                resolution = suggest_resolution(p_event)
                conflicts.append({
                    "personal": p_event['summary'],
                    "work": w_event['summary'],
                    "resolution": resolution
                })
    return conflicts

def suggest_resolution(personal_event: dict) -> str:
    """Provides a suggestion based on the flexibility of the personal event."""
    summary = personal_event.get('summary', '')
    if 'appointment' in summary.lower() or 'vendor' in summary.lower():
        return "High priority constraint. Consider declining the work meeting or requesting a reschedule."
    elif 'reminder' in summary.lower() or 'task' in summary.lower():
        return "Flexible task. The Allie reminder will be shifted to an open slot later in the day."
    return "Review manually."
```

## Cron Automations

### CAL1 - Morning Agenda Briefing
**Schedule:** Daily at 7:00 AM CT
**Model:** Gemini 3 Flash
**Action:** Fetches today's schedule (work and personal) and Allie reminders. Consolidates into a briefing.
**Message Format:**
```
📅 Thursday, July 24

🏢 Work:
• 9:00 AM — Team standup (30 min)
• 2:00 PM — Sprint review (1 hr)

🏠 Personal:
• 5:30 PM — Jack dentist appointment [Allie]

📋 Allie Reminders:
• Freedom Flex Q3 activation — do it today
• HVAC filter due this week

⚠️ No conflicts detected.
```

### CAL2 - Weekly Conflict Scan
**Schedule:** Sunday at 7:00 PM CT
**Model:** Gemini 3 Flash
**Action:** Scans the next 7 days for overlaps between the work schedule and personal calendar.
**Message Format:**
```
⚠️ Schedule Conflict Detected!

📅 Tuesday, July 29
🏢 Work: Q3 Planning Offsite (1:00 PM - 4:00 PM)
🏠 Personal: Plumber Appointment [Allie] (2:00 PM - 3:00 PM)

Suggestion: High priority constraint. Would you like me to find alternative slots for the Plumber appointment?
```

## Resource Files

| File | Purpose | Location |
|------|---------|----------|
| `config.json` | Skill configuration, thresholds, and mappings | `resources/` |

## Integration

| Skill | Read/Write | Description |
|-------|------------|-------------|
| `health-planner` | READ | Reads due/overdue Family Health appointments |
| `financial-planner` | READ | Reads financial reminders (activations, bills) |
| `tax-planner` | READ | Reads quarterly tax deadlines |
| `home-maintenance` | READ | Reads seasonal tasks and vendor appointments |
| `project-board` | READ | Reads task due dates |
| Google Calendar API | WRITE | Creates events and checks freebusy status |

## Data Collection Checklist
Information required from Jon:
- [ ] Google Cloud Project ID
- [ ] `GOOGLE_CALENDAR_CLIENT_ID`
- [ ] `GOOGLE_CALENDAR_CLIENT_SECRET`
- [ ] Execution of the one-time OAuth flow to capture `GOOGLE_CALENDAR_REFRESH_TOKEN`

## Important Notes
> [!IMPORTANT]
> Google Calendar API credentials are a blocking prerequisite for this skill.
> Jon MUST create a Google Cloud project, configure the OAuth Consent Screen, generate Desktop App credentials, and run the OAuth flow to obtain the refresh token before this skill can function.
