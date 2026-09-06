---
name: weekly-fitness-overview
cron_id: weekly-fitness-overview
model: Gemini 3 Flash
schedule: Mondays @ 7:15am
---
## Trigger
Mondays at 7:15am to provide a composite view of overall health and fitness metrics.

## Data Sources
- Workouts DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/Workouts)
- Body Metrics DB (Notion)
- Medications DB (Notion)
- Health Auto Export (`health_data.db` SQLite)
- Lab Results DB (Notion)
- `resources/health_score_weights.json`

## Algorithm
1. Training Consistency: Score based on weekly gym sessions vs 4× target (20%).
2. Sleep Quality: Evaluate average duration and consistency from `health_data.db` (15%).
3. Body Comp Trend: Evaluate weight and BF% trajectory against current goal (cut/bulk/maintain) (15%).
4. Supplement Adherence: Calculate % of supplements taken as scheduled (10%).
5. Recovery Average: Average daily recovery scores (10%).
6. Cardio Fitness & Lab Markers: Score VO2 max trend and % optimal labs (10% each).
7. Combine into a weighted Composite Health Score (0-100) and identify the lowest scoring component for the top actionable recommendation.

## Output Format
🏥 Health Score — [Week Date]

Overall: [Score] / 100 [Emoji]

| Metric               | Score | Contribution | Status |
|-----------------------|-------|--------------|--------|
| Training Consistency  | [Score] | [Weight]     | [Status] |
| Sleep Quality         | [Score] | [Weight]     | [Status] |
| Body Comp Trend       | [Score] | [Weight]     | [Status] |
| Supplement Adherence  | [Score] | [Weight]     | [Status] |

🎯 Top recommendation: [Actionable Advice based on lowest score]
📈 Best metric: [Highest scoring metric]

## Error Handling
- If any data source (e.g., sleep data) is missing, redistribute its weight proportionally among available metrics.
- If Notion DBs fail, send a cached/simplified version or an alert.
