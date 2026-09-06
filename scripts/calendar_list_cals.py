#!/usr/bin/env python3
"""
List all calendars and check today's events on each.
"""
import os, json, sys

client_id = os.environ.get('GOOGLE_CALENDAR_CLIENT_ID')
client_secret = os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET')
refresh_token = os.environ.get('GOOGLE_CALENDAR_REFRESH_TOKEN')

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

# List all calendars
cal_list = service.calendarList().list().execute()
cals = cal_list.get('items', [])
print(f"Found {len(cals)} calendars:")
for c in cals:
    print(f"  - {c.get('summary','?')} (id: {c.get('id','?')}, primary: {c.get('primary',False)})")

# Check primary calendar for today
import datetime
now = datetime.datetime.now(datetime.timezone.utc)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
today_end = today_start + datetime.timedelta(days=2)

print(f"\n--- Events on primary calendar ({today_start.isoformat()} to {today_end.isoformat()}) ---")
events = service.events().list(
    calendarId='primary',
    timeMin=today_start.isoformat(),
    timeMax=today_end.isoformat(),
    singleEvents=True,
    orderBy='startTime',
    maxResults=50
).execute()
items = events.get('items', [])
if not items:
    print("No events found.")
else:
    for e in items:
        start = e['start'].get('dateTime') or e['start'].get('date', '?')
        summary = e.get('summary', 'Untitled')
        print(f"  {start} | {summary}")