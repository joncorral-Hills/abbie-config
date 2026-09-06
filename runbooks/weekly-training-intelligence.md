---
name: weekly-training-intelligence
cron_id: weekly-training-intelligence
model: Gemini 3 Flash
schedule: Sundays @ 7pm
---
## Trigger
Sundays at 7pm to analyze training trends, volume, and plateau risks.

## Data Sources
- Workouts DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/Workouts)
- PRs DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/PRs)
- `exercise_templates.json` (for muscle group mapping)

## Algorithm
1. Muscle Frequency: Map exercises from last 7 days to primary muscle groups. Flag muscles trained < recommended target.
2. Volume Trends: Calculate Σ(weight × reps) per muscle group for this week vs 4-week rolling average. Flag >30% increases (injury risk) or >20% drops.
3. Plateau Detection: Look back 3 sessions per exercise. If max weight×reps is identical across all 3, flag as plateau and suggest micro-load/deload/variation.

## Output Format
🧠 Training Intelligence — Week of [dates]

📊 Volume Summary:
| Muscle Group | This Week | 4-Wk Avg | Trend |
|--------------|-----------|----------|-------|
| [Muscle]     | [Volume]  | [Avg]    | [Trend]|

🔴 Gaps:
• [Muscle]: [Count] sessions this week (target: 2×).

⚠️ Plateaus Detected:
• [Exercise]: Stuck at [Weight] lbs × [Reps] for 3 sessions
  → [Suggestion]

✅ Progressing:
• [Exercise]: [Progression string]

## Error Handling
- If Workouts DB is unreachable, retry after 5 mins.
- If no workouts logged this week, output a recommendation for a deload/recovery week.
