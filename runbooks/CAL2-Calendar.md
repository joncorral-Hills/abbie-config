---
name: CAL2 Calendar
cron_id: cal2-calendar
model: Gemini 3 Flash
schedule: Daily
---
## Trigger
Daily scan for overlaps between work schedule and personal calendar.

## Data Sources
- Google Calendar API: `https://www.googleapis.com/auth/calendar.events` (Requires `GOOGLE_CALENDAR_REFRESH_TOKEN`)
- Work Schedule: Alfred Handoff DB

## Algorithm
1. Fetch personal events for the next 7 days using Google Calendar API `freebusy` or events list.
2. Fetch work events for the next 7 days from the Work Schedule DB.
3. Compare start and end times for overlapping intervals.
4. For any overlap, check event flexibility: summary containing "appointment/vendor" = strict, "reminder/task" = flexible.
5. Generate resolution suggestions based on flexibility.

## Output Format
⚠️ Schedule Conflict Detected!

📅 [Day], [Date]
🏢 Work: [Work Event Title] ([Start] - [End])
🏠 Personal: [Personal Event Title] [Allie] ([Start] - [End])

Suggestion: [Resolution Suggestion based on priority constraint]

## Error Handling
- If Google Calendar API token expires or auth fails, send a Telegram alert requesting a new OAuth flow.
- If Work Schedule DB is unreachable, alert on missing context.
- If no conflicts are detected, either output "⚠️ No conflicts detected." or exit silently depending on user preference.
