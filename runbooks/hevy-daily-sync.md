---
name: hevy-daily-sync
cron_id: hevy-daily-sync
model: Gemini 3 Flash
schedule: Daily @ 10am
---
## Trigger
Daily at 10am. Fetches new workouts and body measurements from Hevy since last sync.

## Data Sources
- Hevy API: `GET /v1/workouts/events?since=TIMESTAMP` using `api-key: $HEVY_API_KEY`
- Hevy API: `GET /v1/workouts/{workoutId}` for changed workouts.
- Hevy API: `GET /v1/body_measurements?page=1`
- Workouts DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/Workouts)
- PRs DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/PRs)

## Algorithm
1. Load `last_workout_sync` timestamp from local sync state.
2. Fetch updated workouts from Hevy API. Convert weight to lbs (kg × 2.20462).
3. Upsert into Notion Workouts DB with calculated total volume (Σ(weight × reps)).
4. Detect PRs: evaluate "normal/failure" working sets using Epley 1RM formula. If estimated 1RM > current PR, upsert PRs DB.
5. Fetch latest body measurements, convert cm to inches (÷ 2.54), upsert to Body Metrics DB.
6. Save new sync state timestamp.

## Output Format
(Silent sync, updates Notion DBs. Sends Telegram message if new PRs detected.)
🎉 New PR Detected!
[Exercise Title]: [Weight] lbs × [Reps] (Estimated 1RM: [1RM] lbs)
Improvement: [Improvement %]%

## Error Handling
- If Hevy API rate limits, backoff and retry.
- If sync state missing, run full backfill (`GET /v1/workouts?page=X`).
- If Hevy API key is invalid, alert Jon via Telegram.
