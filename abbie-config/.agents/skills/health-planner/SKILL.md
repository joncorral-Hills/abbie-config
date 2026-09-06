---
name: health-planner
description: >
  Strategic health intelligence layer for the Corral household. Extends the
  health-automation skill (which handles Hevy sync, Apple Health webhook, lab
  parsing, and supplement management) with eight planning modules: Training
  Intelligence, Recovery Score, Biomarker Trends, Composite Health Score,
  Injury Tracker, Exercise Form Library, Meal Prep Planner, and Family Health
  Calendar. Adds 6 cron jobs and 3 new Notion databases.
requires:
  bins: [python3]
  pip: [scipy]
  env: [NOTION_API_KEY]
---

# Health Planner Skill

## Overview

This skill is the **strategic intelligence layer** that sits on top of the `health-automation` skill (which handles tactical fitness tracking — Hevy workout sync, Apple Health data via Health Auto Export, lab result parsing, and supplement inventory management). Together they form a complete household health and fitness system.

**Dependency**: This skill requires `health-automation` to be active. It reads from the Workouts, PRs, Body Metrics, Medications, Lab Results, and Lab Markers databases created by that skill.

### Architecture

```
health-automation (tactical)                health-planner (strategic)
├── 🏋️ Workouts DB ──────────────────▶  Module A: Training Intelligence
├── 🏆 PRs DB ────────────────────────▶  Module A: Progressive Overload Detection
├── 📏 Body Metrics DB ───────────────▶  Module D: Composite Health Score
│                                         Module G: Meal Prep Planner
├── 💊 Medications DB ────────────────▶  Module D: Supplement Adherence
│                                         H10: Supplement Schedule
├── 🧪 Lab Results DB ────────────────▶  Module C: Biomarker Trend Dashboard
├── 🔬 Lab Markers DB ────────────────▶  Module C: Reference Range Tracking
├── 📱 health_data.db (Auto Export) ──▶  Module B: Recovery Score
│                                         Module D: Sleep + Cardio Scoring
├── exercise_templates.json              Module A: Muscle Group Mapping
└── supplement_timing.json ────────────▶  H10: Supplement Schedule
```

### Notion Integration

- **Health & Fitness page**: `36d63d55-66c5-8125-8c68-ee03bf91096c`
- Databases from `health-automation`: Workouts, PRs, Body Metrics, Medications, Lab Results, Lab Markers
- **New databases** (created by this skill): Injuries, Family Health Calendar, Health Snapshots

---

## Setup (One-Time)

### Step 1: Create New Notion Databases

Create 3 new databases under the Health & Fitness page (`36d63d55-66c5-8125-8c68-ee03bf91096c`).

#### 🩹 Injuries

| Property | Type | Details |
|----------|------|---------|
| Injury Name | Title | e.g., 'Right Shoulder Impingement' |
| Body Part | Select | Options: `Shoulder`, `Knee`, `Back`, `Hip`, `Elbow`, `Wrist`, `Ankle`, `Neck`, `Other` |
| Side | Select | Options: `Left`, `Right`, `Both`, `N/A` |
| Pain Level (1-10) | Number | Current severity |
| Date Reported | Date | When first logged |
| Last Updated | Date | Most recent pain level update |
| Status | Select | Options: `Active`, `Healing`, `Resolved` |
| Exercises to Avoid | Multi-select | From exercise template catalog |
| Substitute Exercises | Rich Text | Alternative movements |
| Treatment | Rich Text | PT exercises, ice/heat, stretches |
| Notes | Rich Text | Recovery progress |

#### 👨‍👩‍👦 Family Health Calendar

| Property | Type | Details |
|----------|------|---------|
| Event | Title | e.g., 'Jon — Annual Physical' |
| Person | Select | Options: `Jon`, `Jaime`, `Jack` |
| Type | Select | Options: `Physical`, `Dental`, `Eye`, `Dermatology`, `Vaccination`, `Well-Visit`, `Specialist`, `Lab Work` |
| Last Completed | Date | When last done |
| Frequency | Select | Options: `Annual`, `Semi-Annual`, `Quarterly`, `One-Time` |
| Next Due | Formula | `dateAdd(prop("Last Completed"), prop("Frequency interval"))` |
| Provider | Rich Text | Doctor name / clinic |
| Status | Select | Options: `Scheduled`, `Due`, `Overdue`, `Completed` |
| Insurance Notes | Rich Text | Coverage info, referral needed, copay |
| Prep Instructions | Rich Text | Fasting required, bring records, etc. |

#### 📸 Health Snapshots

| Property | Type | Details |
|----------|------|---------|
| Snapshot Date | Title | YYYY-MM format |
| Health Score | Number | 0-100 composite from Module D |
| Training Score | Number | Component score |
| Overload Score | Number | Component score |
| Sleep Score | Number | Component score |
| Body Comp Score | Number | Component score |
| Supplement Score | Number | Component score |
| Recovery Score | Number | Component score (30-day avg) |
| Cardio Score | Number | Component score |
| Lab Score | Number | Component score |
| MoM Change | Number | This month minus last month |
| Top Action | Rich Text | Highest-impact recommendation |
| Notes | Rich Text | Major events, changes |

### Step 2: Seed Family Health Calendar

Load the recommended preventive care schedule into the Family Health Calendar DB:

| Person | Type | Frequency |
|--------|------|-----------|
| Jon | Annual Physical | Annual |
| Jon | Dental Cleaning | Semi-Annual |
| Jon | Eye Exam | Annual |
| Jon | Dermatology (skin check) | Annual |
| Jon | Lab Work (comprehensive) | Annual (with physical) |
| Jaime | Annual Physical | Annual |
| Jaime | Dental Cleaning | Semi-Annual |
| Jaime | Eye Exam | Annual |
| Jaime | OB/GYN | Annual |
| Jack | Well-Visit (pediatric) | Annual |
| Jack | Dental Cleaning | Semi-Annual |
| All | Flu Vaccine | Annual (Sept-Oct) |

Set all `Last Completed` dates to the most recent known visit. Mark any unknown dates as `Overdue` status.

### Step 3: Collect Missing Data from Jon

Before the system is fully operational, Jon must provide:

1. **Last physical date** for Jon, Jaime, and Jack
2. **Last dental cleaning date** for each family member
3. **Active injuries** (any current pain or movement restrictions)
4. **Goal direction** (cut/bulk/maintain) and target bodyweight
5. **Dietary preferences or restrictions** (for Meal Prep Planner)
6. **Apple Health data access confirmation** (Health Auto Export configured and writing to health_data.db)

Store responses in the respective resource files and Notion databases.

---

## Module A: Training Intelligence

### Purpose
Detect training plateaus before they become stalls, ensure balanced muscle group coverage, and track volume trends to prevent overtraining or detraining.

### Progressive Overload Detection

For each exercise performed in the last week, look back 3 sessions. If weight×reps hasn't increased across 3 consecutive sessions, flag as plateau.

```python
def check_plateau(exercise_id, lookback_sessions=3):
    history = hevy_api.get_exercise_history(exercise_id)
    # Get best working set (highest weight×reps product, excluding warmup) from each session
    best_sets = []
    for session in history[-lookback_sessions:]:
        working_sets = [s for s in session.sets if s.type != 'warmup']
        if working_sets:
            best = max(working_sets, key=lambda s: (s.weight_kg or 0) * (s.reps or 0))
            best_sets.append(best)
    
    if len(best_sets) >= 3:
        # Check if all 3 sessions have same weight and reps
        same_weight = all(s.weight_kg == best_sets[0].weight_kg for s in best_sets)
        same_reps = all(s.reps == best_sets[0].reps for s in best_sets)
        if same_weight and same_reps:
            return generate_plateau_suggestions(exercise_id, best_sets[0])
    return None

def generate_plateau_suggestions(exercise_id, stuck_set):
    weight_lbs = stuck_set.weight_kg * 2.20462
    return {
        "exercise": get_exercise_name(exercise_id),
        "stuck_at": f"{weight_lbs:.0f} lbs × {stuck_set.reps}",
        "suggestions": [
            f"Micro-load: Add 5 lbs → {weight_lbs + 5:.0f} lbs × {stuck_set.reps}",
            f"Rep push: Same weight → {weight_lbs:.0f} lbs × {stuck_set.reps + 2}",
            f"Intensity: Reduce reps, add weight → {weight_lbs + 10:.0f} lbs × {max(1, stuck_set.reps - 2)}",
            f"Deload: Drop to {weight_lbs * 0.85:.0f} lbs × 8-10 for 1 week, then rebuild",
            f"Variation: Swap exercise for 3-4 weeks, then return"
        ]
    }
```

### Muscle Group Frequency Analysis

- Pull last 7 days of workouts from Workouts DB
- Map exercises → primary muscle groups via `exercise_templates.json`
- Compare against recommended frequency (most groups: 2×/week)
- Flag gaps: "You haven't hit legs in 8 days"
- Flag overtraining: "Chest hit 3× this week — consider recovery"

**Muscle group list**: chest, back (lats + upper_back + traps), shoulders, biceps, triceps, forearms, quadriceps, hamstrings, glutes, calves, abdominals, lower_back

```python
def analyze_muscle_frequency(days=7):
    workouts = query_workouts_db(last_n_days=days)
    frequency = defaultdict(list)  # muscle_group → [dates_trained]
    
    for workout in workouts:
        for exercise in workout.exercises:
            muscle_group = get_primary_muscle_group(exercise.template_id)
            frequency[muscle_group].append(workout.date)
    
    # Recommended frequencies per week
    recommended = {
        'chest': 2, 'back': 2, 'shoulders': 2,
        'biceps': 2, 'triceps': 2, 'forearms': 1,
        'quadriceps': 2, 'hamstrings': 2, 'glutes': 2,
        'calves': 2, 'abdominals': 3, 'lower_back': 1
    }
    
    alerts = []
    for muscle, target in recommended.items():
        sessions = len(set(frequency.get(muscle, [])))
        days_since = (date.today() - max(frequency.get(muscle, [date.min]))).days
        
        if sessions == 0 and target >= 2:
            alerts.append(f"🔴 You haven't hit {muscle} in {days_since}+ days")
        elif sessions < target:
            alerts.append(f"🟡 {muscle}: {sessions}× this week (target: {target}×)")
        elif sessions > target + 1:
            alerts.append(f"⚠️ {muscle}: hit {sessions}× this week — consider recovery")
    
    return alerts
```

### Weekly Volume Tracking

- Total volume = Σ(weight_lbs × reps) per muscle group per week
- Track 4-week rolling average
- Alert if weekly volume drops >20% vs 4-week average
- Alert if weekly volume increases >30% (injury risk from sudden jumps)

```python
def check_volume_trends(muscle_group, weeks_back=4):
    weekly_volumes = []
    for week_offset in range(weeks_back + 1):  # current + 4 prior
        start = today - timedelta(weeks=week_offset, days=today.weekday())
        end = start + timedelta(days=6)
        volume = sum(
            set.weight_kg * 2.20462 * set.reps
            for workout in get_workouts(start, end)
            for exercise in workout.exercises
            if get_primary_muscle_group(exercise.template_id) == muscle_group
            for set in exercise.sets if set.type != 'warmup'
        )
        weekly_volumes.append(volume)
    
    current_week = weekly_volumes[0]
    rolling_avg = sum(weekly_volumes[1:]) / len(weekly_volumes[1:]) if weekly_volumes[1:] else 0
    
    if rolling_avg > 0:
        pct_change = (current_week - rolling_avg) / rolling_avg * 100
        if pct_change < -20:
            return f"📉 {muscle_group} volume down {abs(pct_change):.0f}% vs 4-week avg"
        elif pct_change > 30:
            return f"📈 {muscle_group} volume up {pct_change:.0f}% vs 4-week avg — injury risk!"
    return None
```

### Training Intelligence Report Format (Sunday 7:15 PM)

```
🧠 Training Intelligence — Week of [dates]

📊 Volume Summary:
| Muscle Group | This Week | 4-Wk Avg | Trend |
|--------------|-----------|----------|-------|
| Chest        | 12,500    | 11,800   | ↑ 6%  |
| Back         | 15,200    | 14,900   | → 2%  |
| Legs         | 0         | 9,500    | 🔴 -100% |
| Shoulders    | 6,800     | 7,200    | ↓ 6%  |
| Arms         | 8,100     | 7,500    | ↑ 8%  |

🔴 Gaps:
• Legs: 0 sessions this week (target: 2×). Last hit 9 days ago.

⚠️ Plateaus Detected:
• Bench Press (Barbell): Stuck at 185 lbs × 8 for 3 sessions
  → Micro-load: Try 190 lbs × 8
  → Or rep push: 185 lbs × 10

✅ Progressing:
• Squat (Barbell): 225→235→245 lbs over last 3 sessions 🔥
• Pull Up: BW+25→BW+35 lbs this month
```

---

## Module B: Recovery Score (0-100 Daily)

### Purpose
Daily readiness assessment that synthesizes sleep, HRV, heart rate, training status, and subjective soreness into a single actionable score.

### Data Sources & Weights

| Metric | Weight | Source | Scoring |
|--------|--------|--------|---------|
| Sleep Duration | 25% | Health Auto Export (health_data.db) | ≥7.5hr = 100, ≤5hr = 0, linear between |
| Sleep Consistency | 10% | Health Auto Export | Bedtime variance <30min = 100, >2hr = 0 |
| HRV | 20% | Health Auto Export | Above 30-day personal avg = 100, decreasing scale below |
| Resting Heart Rate | 15% | Health Auto Export | Below 30-day avg = 100, increasing scale above |
| Training Recency | 15% | Hevy workouts | 1-2 days since last = 100, 0 days = 60 (just trained), 3+ days = decreasing |
| Soreness (optional) | 15% | Telegram self-report | 1/5 = 100, 5/5 = 0. If not reported, redistribute weight to other metrics |

### Recovery Score Algorithm

```python
def calculate_recovery_score(health_data, last_workout_date, soreness=None):
    scores = {}
    weights = {}
    
    # Sleep duration (25%)
    sleep_hours = health_data.get_last_night_sleep_hours()
    scores['sleep_duration'] = min(100, max(0, (sleep_hours - 5) / 2.5 * 100))
    weights['sleep_duration'] = 0.25
    
    # Sleep consistency (10%)
    bedtime_variance_min = health_data.get_bedtime_variance_minutes(days=7)
    scores['sleep_consistency'] = min(100, max(0, (120 - bedtime_variance_min) / 90 * 100))
    weights['sleep_consistency'] = 0.10
    
    # HRV (20%)
    current_hrv = health_data.get_latest('heart_rate_variability')
    avg_hrv = health_data.get_average('heart_rate_variability', days=30)
    if avg_hrv and current_hrv:
        hrv_ratio = current_hrv / avg_hrv
        scores['hrv'] = min(100, max(0, hrv_ratio * 80))  # 1.25× avg = 100
    else:
        scores['hrv'] = 50  # neutral if no data
    weights['hrv'] = 0.20
    
    # Resting HR (15%)
    current_rhr = health_data.get_latest('resting_heart_rate')
    avg_rhr = health_data.get_average('resting_heart_rate', days=30)
    if avg_rhr and current_rhr:
        rhr_ratio = avg_rhr / current_rhr  # lower is better
        scores['resting_hr'] = min(100, max(0, rhr_ratio * 80))
    else:
        scores['resting_hr'] = 50
    weights['resting_hr'] = 0.15
    
    # Training recency (15%)
    days_since = (date.today() - last_workout_date).days
    if days_since == 0: scores['training_recency'] = 60
    elif days_since in (1, 2): scores['training_recency'] = 100
    elif days_since == 3: scores['training_recency'] = 80
    elif days_since == 4: scores['training_recency'] = 60
    else: scores['training_recency'] = 40
    weights['training_recency'] = 0.15
    
    # Soreness (15%)
    if soreness is not None:
        scores['soreness'] = max(0, (5 - soreness) / 4 * 100)
        weights['soreness'] = 0.15
    else:
        # Redistribute to other metrics proportionally
        pass
    
    # Normalize weights if soreness missing
    total_weight = sum(weights.values())
    return sum(scores[k] * weights[k] / total_weight for k in scores)
```

### Output Format (Telegram, 7:00 AM)

```
🔋 Recovery Score: 78/100 ✅

😴 Sleep: 7.2 hrs (94%) — Bedtime 10:45 PM ✅
💓 HRV: 42ms (↑ from 38ms avg) ✅
❤️ Resting HR: 58 bpm (→ at avg) ➡️
🏋️ Last session: Yesterday (Chest & Triceps) ✅
😤 Soreness: not reported

→ Good to train. Suggested: Back & Biceps (last hit 3 days ago)
```

### Score Interpretation

| Range | Rating | Recommendation |
|-------|--------|----------------|
| 90-100 | Excellent 🟢 | Push hard — PR attempt day |
| 75-89 | Good ✅ | Normal training intensity |
| 60-74 | Fair ⚠️ | Moderate intensity, skip heavy compounds |
| 40-59 | Low 🔶 | Light session or active recovery only |
| 0-39 | Rest 🔴 | Take the day off |

### Training Suggestion Logic

After computing the recovery score, suggest today's workout based on:

1. Recovery score → intensity level
2. Muscle group frequency gaps (Module A) → what to train
3. Active injuries (Module E) → what to avoid

```python
def suggest_workout(recovery_score, frequency_gaps, active_injuries):
    restrictions = get_exercise_restrictions()  # from Module E
    
    if recovery_score < 40:
        return "Rest day recommended. Light walk or stretching only."
    
    if recovery_score < 60:
        return f"Active recovery: Light cardio, mobility work, foam rolling."
    
    # Pick the muscle group with the longest gap
    if frequency_gaps:
        target_muscle = max(frequency_gaps, key=lambda g: g.days_since_last)
        intensity = "normal" if recovery_score >= 75 else "moderate"
        
        # Filter restricted exercises
        safe_exercises = get_exercises_for_muscle(
            target_muscle, exclude=restrictions.keys()
        )
        return {
            "target": target_muscle,
            "intensity": intensity,
            "exercises": safe_exercises,
            "pr_attempt": recovery_score >= 90
        }
```

---

## Module C: Biomarker Trend Dashboard

### Purpose
Track lab markers over time with trajectory analysis. Identify trends before they become problems and validate supplement/lifestyle interventions.

### Data Flow

1. Query Lab Results DB sorted by date for each marker in Lab Markers DB
2. Calculate slope via linear regression over last 3+ labs
3. Color code: 🟢 optimal + improving/stable, 🟡 in range but trending wrong, 🔴 out of optimal
4. Generate quarterly report via Google Chat

### Trend Calculation

```python
from scipy.stats import linregress

def calculate_biomarker_trends(marker_name, min_datapoints=3):
    results = query_lab_results_db(marker=marker_name, sort='date_asc')
    
    if len(results) < min_datapoints:
        return {"status": "insufficient_data", "count": len(results)}
    
    # Linear regression for trend
    x = [(r.date - results[0].date).days for r in results]
    y = [r.value for r in results]
    slope, intercept, r_value, p_value, std_err = linregress(x, y)
    
    # Get reference range from Lab Markers DB
    marker = query_lab_markers_db(name=marker_name)
    optimal_low, optimal_high = marker.optimal_range
    
    current = results[-1].value
    prior = results[-2].value if len(results) >= 2 else None
    pct_change = ((current - prior) / prior * 100) if prior else None
    
    # Determine status
    in_optimal = optimal_low <= current <= optimal_high
    improving = (slope > 0 and marker.higher_is_better) or \
                (slope < 0 and not marker.higher_is_better)
    
    if in_optimal and (improving or abs(slope) < 0.01):
        status = "🟢"
    elif in_optimal and not improving:
        status = "🟡↓" if not marker.higher_is_better else "🟡↑"
    else:
        status = "🔴"
    
    return {
        "marker": marker_name,
        "current": current,
        "prior": prior,
        "pct_change": pct_change,
        "trend_direction": "↑" if slope > 0 else "↓",
        "optimal_range": f"{optimal_low}-{optimal_high}",
        "status": status,
        "slope_per_month": slope * 30  # normalize to monthly rate
    }
```

### Priority Action Generator

```python
def generate_priority_actions(trends):
    actions = []
    for t in trends:
        if t['status'] == '🔴':
            marker = t['marker']
            if marker == 'Vitamin D' and t['current'] < 40:
                actions.append(f"Vitamin D below optimal ({t['current']} ng/mL) — supplement 5000 IU D3 daily with fatty meal")
            elif marker == 'Total Cholesterol' and t['current'] > 200:
                actions.append(f"Total Cholesterol elevated ({t['current']}) — increase soluble fiber, consider omega-3s")
            elif marker == 'Testosterone' and t['current'] < 500:
                actions.append(f"Testosterone low ({t['current']}) — prioritize sleep, zinc, strength training")
            # ... additional marker-specific advice
    return actions
```

### Quarterly Report Format (Google Chat)

```
🧪 Biomarker Trends — Q2 2026

| Marker | Current | Prior | Trend | Optimal | Status |
|--------|---------|-------|-------|---------|--------|
| Total Cholesterol | 195 | 210 | ↓ 7% | <180 | 🟡 |
| HDL | 52 | 47 | ↑ 11% | >60 | 🟡↑ |
| LDL | 115 | 128 | ↓ 10% | <100 | 🟡↓ |
| Triglycerides | 140 | 160 | ↓ 13% | <150 | 🟢 |
| Vitamin D | 28 | 45 | ↓ 38% | 40-60 | 🔴 |
| Testosterone | 550 | 520 | ↑ 6% | 500-900 | 🟢 |
| Fasting Glucose | 92 | 95 | ↓ 3% | 70-99 | 🟢 |
| A1c | 5.4 | 5.5 | ↓ 2% | <5.7 | 🟢 |
| TSH | 2.1 | 2.3 | ↓ 9% | 0.5-4.5 | 🟢 |
| Vitamin B12 | 450 | 480 | ↓ 6% | 400-1100 | 🟢 |

🎯 Priority Action: Vitamin D below optimal — supplement 5000 IU D3 daily with fatty meal
📈 Best Trend: HDL up 11% — cardiovascular health improving
📉 Watch: Total Cholesterol in range but above optimal target of <180
```

---

## Module D: Composite Health Score (0-100 Monthly)

### Purpose
Single composite score (0–100) that quantifies overall household fitness and health. Makes progress tangible and identifies the highest-impact area to focus on.

### Data Source
`resources/health_score_weights.json` — Metric definitions, weights, and thresholds.

### Scoring Formula

```
Health Score = Σ (metric_score × weight)

Where:
  training_consistency  × 0.20  (from Workouts DB — sessions/week vs 4× target)
+ progressive_overload  × 0.10  (from PRs DB + exercise history)
+ sleep_quality         × 0.15  (from Health Auto Export — avg hours + consistency)
+ body_composition      × 0.15  (from Body Metrics DB — weight + BF% trend)
+ supplement_adherence  × 0.10  (from Medications DB — % taken as scheduled)
+ recovery_average      × 0.10  (from Module B — 30-day average recovery score)
+ cardio_fitness        × 0.10  (from Health Auto Export — VO2 max trend)
+ lab_markers           × 0.10  (from Lab Results DB — % of markers in optimal range)
```

### Metric Calculations

#### 1. Training Consistency (20%)

```python
def training_consistency_score():
    """Weekly gym sessions vs 4× target, averaged over the month."""
    weeks = get_weeks_in_month(current_month)
    scores = []
    for week_start, week_end in weeks:
        sessions = count_workouts(week_start, week_end)
        target = 4
        week_score = min(100, (sessions / target) * 100)
        scores.append(week_score)
    return sum(scores) / len(scores)
```

#### 2. Progressive Overload (10%)

```python
def progressive_overload_score():
    """% of regularly performed exercises showing progression."""
    exercises = get_exercises_performed(last_n_days=30, min_sessions=3)
    progressing = 0
    for exercise in exercises:
        history = get_exercise_history(exercise.template_id, sessions=3)
        best_volumes = [max(s.weight_kg * s.reps for s in sess.working_sets) for sess in history]
        if best_volumes[-1] > best_volumes[0]:  # most recent > oldest
            progressing += 1
    return (progressing / len(exercises) * 100) if exercises else 50
```

#### 3. Sleep Quality (15%)

```python
def sleep_quality_score():
    """Combines average sleep duration and consistency."""
    avg_hours = health_data.get_average('sleep_duration_hours', days=30)
    variance_min = health_data.get_bedtime_variance_minutes(days=30)
    
    duration_score = min(100, max(0, (avg_hours - 5) / 2.5 * 100))
    consistency_score = min(100, max(0, (120 - variance_min) / 90 * 100))
    
    return duration_score * 0.70 + consistency_score * 0.30
```

#### 4. Body Composition Trend (15%)

```python
def body_composition_score():
    """Are weight and body fat % moving toward goals?"""
    metrics = query_body_metrics_db(last_n_days=30)
    if len(metrics) < 2:
        return 50  # neutral until data
    
    goal = get_body_comp_goal()  # 'cut', 'bulk', 'maintain'
    weight_trend = metrics[-1].weight_lbs - metrics[0].weight_lbs
    bf_trend = (metrics[-1].body_fat_pct - metrics[0].body_fat_pct) if metrics[0].body_fat_pct else None
    
    if goal == 'cut':
        # Want: weight down, BF% down
        weight_score = 100 if weight_trend < 0 else max(0, 100 - weight_trend * 10)
        bf_score = 100 if (bf_trend and bf_trend < 0) else 50
    elif goal == 'bulk':
        # Want: weight up, BF% stable or down
        weight_score = 100 if weight_trend > 0 else max(0, 100 - abs(weight_trend) * 10)
        bf_score = 100 if (bf_trend and bf_trend <= 0.5) else 50
    else:  # maintain
        # Want: weight stable (±2 lbs)
        weight_score = 100 if abs(weight_trend) <= 2 else max(0, 100 - abs(weight_trend) * 15)
        bf_score = 100 if (bf_trend and abs(bf_trend) <= 0.5) else 50
    
    return weight_score * 0.6 + bf_score * 0.4
```

#### 5. Supplement Adherence (10%)

```python
def supplement_adherence_score():
    """% of scheduled supplements taken on time."""
    scheduled = query_medications_db(month=current_month, type='supplement')
    taken = sum(1 for s in scheduled if s.status == 'taken')
    total = len(scheduled)
    return (taken / total * 100) if total else 100
```

#### 6. Recovery Average (10%)

```python
def recovery_average_score():
    """30-day average of daily recovery scores from Module B."""
    daily_scores = get_recovery_scores(last_n_days=30)
    if not daily_scores:
        return 50
    return sum(daily_scores) / len(daily_scores)
```

#### 7. Cardio Fitness (10%)

```python
def cardio_fitness_score():
    """VO2 max trend from Apple Health."""
    current_vo2 = health_data.get_latest('vo2_max')
    avg_vo2 = health_data.get_average('vo2_max', days=90)
    
    if not current_vo2:
        return 50  # neutral if no data
    
    # Age-adjusted percentile (Jon, assuming 30-39 age range)
    # Superior: >51.1, Excellent: 45.4-51.1, Good: 41.0-45.3
    if current_vo2 >= 51.1: base = 100
    elif current_vo2 >= 45.4: base = 85
    elif current_vo2 >= 41.0: base = 70
    elif current_vo2 >= 36.7: base = 55
    else: base = 40
    
    # Trend bonus/penalty
    if avg_vo2 and current_vo2 > avg_vo2:
        base = min(100, base + 5)
    elif avg_vo2 and current_vo2 < avg_vo2 * 0.95:
        base = max(0, base - 10)
    
    return base
```

#### 8. Lab Markers (10%)

```python
def lab_markers_score():
    """% of tracked markers within optimal range."""
    markers = query_lab_markers_db()
    in_optimal = 0
    for marker in markers:
        latest = get_latest_lab_result(marker.name)
        if latest and marker.optimal_low <= latest.value <= marker.optimal_high:
            in_optimal += 1
    return (in_optimal / len(markers) * 100) if markers else 50
```

### Score Interpretation

| Range | Rating | Emoji | Meaning |
|-------|--------|-------|---------|
| 90–100 | Excellent | 🏆 | All metrics green. Maintain course. |
| 75–89 | Good | ✅ | Minor areas for improvement. |
| 60–74 | Fair | ⚠️ | Several areas need attention. |
| 40–59 | Needs Work | 🔶 | Significant health/fitness stress. |
| 0–39 | Critical | 🚨 | Major intervention required. |

### Actionable Recommendations Engine

```python
def get_top_recommendation(metrics):
    """Find the metric with lowest score × highest weight = biggest improvement potential."""
    potential = [(name, (100 - score) * weight) for name, score, weight in metrics]
    worst = max(potential, key=lambda x: x[1])
    
    recommendations = {
        "training_consistency": "Get to the gym — consistency is the #1 predictor of results.",
        "progressive_overload": "Focus on adding 5 lbs or 1-2 reps per exercise this week.",
        "sleep_quality": "Get to bed by 10:30 PM — sleep is your #1 bottleneck.",
        "body_composition": f"Adjust calorie intake. Current goal: {goal}. Stay disciplined this week.",
        "supplement_adherence": "Set phone alarms for AM and PM supplements. Don't skip.",
        "recovery_average": "You're under-recovered. Prioritize sleep and reduce training volume.",
        "cardio_fitness": "Add 2 zone-2 cardio sessions this week (30 min walk/jog/bike).",
        "lab_markers": "Review out-of-range markers with your doctor. See biomarker trends."
    }
    return recommendations[worst[0]]
```

### Monthly Health Report Format (Google Chat, 1st of month)

```
🏥 Health Score — June 2026

Overall: 71 / 100 ⚠️ (↑ from 65 last month)

| Metric               | Score | Weight | Contribution | Status |
|-----------------------|-------|--------|--------------|--------|
| Training Consistency  | 85    | 20%    | 17.0         | 🟢     |
| Progressive Overload  | 60    | 10%    | 6.0          | ⚠️     |
| Sleep Quality         | 48    | 15%    | 7.2          | 🔴     |
| Body Comp Trend       | 70    | 15%    | 10.5         | 🟢     |
| Supplement Adherence  | 95    | 10%    | 9.5          | 🟢     |
| Recovery Average      | 68    | 10%    | 6.8          | ⚠️     |
| Cardio Fitness        | 75    | 10%    | 7.5          | 🟢     |
| Lab Markers           | 90    | 10%    | 9.0          | 🟢     |

🎯 Top recommendation: Get to bed by 10:30 PM — sleep is your #1 bottleneck
📈 Best metric: Supplement Adherence at 95 — keep it up!
📉 Biggest opportunity: Sleep at 48 — adds 7.8 points if improved to 80
```

---

## Module E: Injury & Pain Tracker

### Purpose
Track active injuries, cross-reference against training plans to prevent aggravation, and suggest safe exercise substitutions.

### Database
Uses the **Injuries DB** created in Setup Step 1 (schema documented above).

### Training Integration

When generating workout suggestions in Module A or Recovery Score in Module B, cross-reference active injuries:

```python
def get_exercise_restrictions():
    active_injuries = query_injuries_db(status='Active')
    restrictions = {}
    for injury in active_injuries:
        for exercise in injury.exercises_to_avoid:
            restrictions[exercise] = {
                'reason': f'{injury.injury_name} (pain: {injury.pain_level}/10)',
                'substitute': injury.substitute_exercises
            }
    return restrictions
```

### Post-Workout Safety Check

When Hevy sync detects a restricted exercise was performed, send an alert via Telegram:

```
⚠️ You performed Overhead Press today, but it's on your avoid list due to
Right Shoulder Impingement (pain: 6/10).

Consider using Landmine Press instead.

Update injury status? Reply:
• "pain 4" — update pain level to 4/10
• "healing" — mark as healing
• "resolved" — clear the restriction
```

### Pain Level Tracking Over Time

```python
def check_injury_progress():
    """Weekly check: is each active injury improving or worsening?"""
    active = query_injuries_db(status__in=['Active', 'Healing'])
    alerts = []
    for injury in active:
        # Compare current pain to when first reported
        if injury.pain_level <= 2 and injury.status == 'Active':
            alerts.append(
                f"✅ {injury.injury_name} pain dropped to {injury.pain_level}/10 "
                f"— consider marking as 'Healing'"
            )
        elif (date.today() - injury.last_updated).days > 14:
            alerts.append(
                f"🔔 {injury.injury_name} hasn't been updated in "
                f"{(date.today() - injury.last_updated).days} days. "
                f"How's the pain?"
            )
    return alerts
```

---

## Module F: Exercise Form & Technique Library

### Purpose
Provide real-time form coaching when a user performs an exercise for the first time. Stored in `resources/exercise_library.json`.

### Data Structure

For each common exercise:
- `exercise_name`: Matching Hevy naming convention (e.g., 'Bench Press (Barbell)')
- `primary_muscle_group`: Primary target muscle
- `technique_cues`: 3-5 key form points
- `common_mistakes`: 2-3 things to avoid
- `warmup_recommendation`: Suggested warmup before this exercise
- `muscle_activation`: What you should feel working

### Trigger Logic

Fires when Hevy sync detects a user performing an exercise for the first time (no prior history for that `exercise_template_id`).

```python
def check_new_exercises(workout):
    """After Hevy sync, check if any exercises are brand new for this user."""
    for exercise in workout.exercises:
        history = hevy_api.get_exercise_history(exercise.template_id)
        if len(history) <= 1:  # This workout is the only one
            form_tips = get_exercise_form(exercise.template_id)
            if form_tips:
                send_form_coaching(form_tips)

def get_exercise_form(template_id):
    """Look up form cues from exercise_library.json."""
    exercise_name = get_exercise_name(template_id)
    with open('resources/exercise_library.json') as f:
        library = json.load(f)
    for entry in library['exercises']:
        if entry['exercise_name'] == exercise_name:
            return entry
    return None
```

### Telegram Message Format

```
🎓 First time doing Romanian Deadlift (Barbell)!

✅ Form cues:
• Hinge at hips, not waist — push hips back
• Keep bar close to shins throughout
• Slight knee bend (not a stiff-leg deadlift)
• Feel the stretch in hamstrings at bottom
• Squeeze glutes to return to top

⚠️ Common mistakes:
• Rounding lower back (keep chest proud)
• Going too heavy too soon
• Bending knees too much (this isn't a squat)

🔥 Warmup: 2 sets of 10 bodyweight hip hinges, then 1 set at 50% working weight
💪 You should feel: Deep stretch in hamstrings, glutes contracting at the top
```

---

## Module G: Meal Prep Planner

### Purpose
Generate weekly meal prep plans calibrated to training goals, bodyweight targets, and budget constraints.

### Trigger
On-demand — triggered by user request via chat.

### Calculation Pipeline

```python
def generate_meal_plan():
    # 1. Get body metrics and goal
    metrics = query_body_metrics_db(latest=True)
    current_weight_lbs = metrics.weight_lbs
    goal = get_body_comp_goal()  # 'cut', 'bulk', 'maintain'
    target_weight_lbs = get_target_weight()
    
    # 2. Calculate macros
    protein_g = target_weight_lbs  # 1g per lb of target bodyweight
    
    calorie_multipliers = {'cut': 12, 'maintain': 15, 'bulk': 18}
    calories = target_weight_lbs * calorie_multipliers[goal]
    
    protein_cals = protein_g * 4
    fat_cals = calories * 0.25  # 25% from fat
    fat_g = fat_cals / 9
    carb_cals = calories - protein_cals - fat_cals
    carb_g = carb_cals / 4
    
    # 3. Check grocery budget (from financial system if available)
    try:
        budget = get_grocery_budget()  # from financial-automation
    except:
        budget = 150  # default weekly budget
    
    # 4. Generate plan via LLM reasoning
    plan = generate_plan_with_llm(
        calories=calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carb_g=carb_g,
        budget=budget,
        goal=goal,
        preferences=get_dietary_preferences()
    )
    
    return plan
```

### Output Format

```
🍽️ Meal Prep Plan — Week of [dates]

Target: 180g protein / 2,400 cal (cutting)
Macros: 180g P / 67g F / 240g C
Budget: $150/week groceries

Mon-Wed:
  Breakfast: Greek yogurt parfait (40g P, 350 cal — $2.50)
  Lunch: Chicken rice bowl (45g P, 520 cal — $3.00)
  Dinner: Salmon + sweet potato + broccoli (42g P, 580 cal — $5.50)
  Snack: Protein shake + banana (30g P, 280 cal — $1.50)
  Daily: 157g protein, 2,350 cal, $12.50

Thu-Sat:
  Breakfast: Egg white scramble + toast (35g P, 320 cal — $2.00)
  Lunch: Turkey wrap + greek yogurt (40g P, 480 cal — $3.50)
  Dinner: Ground turkey stir fry (38g P, 550 cal — $4.00)
  Snack: Cottage cheese + berries (25g P, 250 cal — $1.50)
  Daily: 138g protein, 2,200 cal, $11.00

Sun (Refeed):
  Higher carb day — 2,800 cal target
  Pancake breakfast, pasta lunch, normal dinner

🛒 Grocery List:
- Chicken breast 5 lbs — $12
- Ground turkey 3 lbs — $9
- Salmon fillets 2 lbs — $14
- Greek yogurt 32oz × 2 — $10
- Eggs 18ct — $4
- Rice 5 lbs — $5
- Sweet potatoes 3 lbs — $4
- Broccoli 3 lbs — $5
- Mixed vegetables — $6
- Protein powder (on hand) — $0
- Pantry staples — $15
...

Estimated total: $135 (under $150 budget ✅)
Prep time: ~3 hours Sunday
```

---

## Module H: Family Health Calendar

### Purpose
Never miss a preventive care appointment. Track all family members' medical visits, vaccinations, and screenings with proactive reminders.

### Database
Uses the **Family Health Calendar DB** created in Setup Step 1 (schema documented above).

### Weekly Scan Logic (Monday 8:00 AM)

```python
def check_upcoming_health_events():
    events = query_family_health_db()
    alerts = []
    for event in events:
        days_until = (event.next_due - date.today()).days
        
        if event.status == 'Overdue' or days_until < 0:
            alerts.append(
                f'🔴 OVERDUE: {event.event} — was due {event.next_due.strftime("%b %d")}. '
                f'Schedule ASAP!'
            )
        elif days_until <= 30:
            if event.status != 'Scheduled':
                alerts.append(
                    f'🟡 DUE SOON: {event.event} — due {event.next_due.strftime("%b %d")}. '
                    f'Schedule it!'
                )
            else:
                alerts.append(
                    f'✅ SCHEDULED: {event.event} — coming up {event.next_due.strftime("%b %d")}'
                )
        elif days_until <= 60:
            alerts.append(
                f'🟢 UPCOMING: {event.event} — due {event.next_due.strftime("%b %d")} '
                f'({days_until} days)'
            )
    return alerts
```

### Telegram Alert Format

```
🏥 Family Health Calendar — Week of [dates]

🔴 OVERDUE:
• Jon — Dental Cleaning — was due Apr 15. Schedule ASAP!
• Jaime — Eye Exam — was due Mar 1. Schedule ASAP!

🟡 DUE SOON (next 30 days):
• Jack — Well-Visit (pediatric) — due Jul 8. Schedule it!

🟢 UPCOMING (30-60 days):
• Jon — Annual Physical — due Aug 12 (63 days)

✅ SCHEDULED:
• All — Flu Vaccine — Oct 1 (scheduled)
```

### Auto-Update on Completion

When a user reports that an appointment was completed:
1. Set `Last Completed` to today (or specified date)
2. Set `Status` to `Completed`
3. Recalculate `Next Due` based on frequency
4. Reset `Status` to `Due` (for the next occurrence)

```python
def mark_appointment_complete(event_id, completion_date=None):
    event = get_event(event_id)
    completed = completion_date or date.today()
    
    frequency_days = {
        'Annual': 365,
        'Semi-Annual': 182,
        'Quarterly': 91,
        'One-Time': None
    }
    
    update_event(event_id, {
        'Last Completed': completed,
        'Status': 'Completed' if event.frequency == 'One-Time' else 'Due',
        'Next Due': completed + timedelta(days=frequency_days[event.frequency])
            if event.frequency != 'One-Time' else None
    })
```

---

## Cron Automations

This skill adds 6 new cron jobs. These are IN ADDITION to the 4 crons in `health-automation`.

### H5. Recovery Score
- **Schedule**: Daily 7:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Calculate Module B recovery score from health_data.db + Hevy. Optionally prompt for soreness via Telegram (wait 5 min for response, proceed without if no reply). Send recovery report with workout suggestion.

### H6. Training Intelligence
- **Schedule**: Sunday 7:15 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Run Module A: plateau detection for all exercises performed this week, muscle group frequency analysis (7-day window), weekly volume tracking vs 4-week rolling average. Append insights to weekly training summary from H3.

### H7. Composite Health Score
- **Schedule**: 1st of month, 8:30 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Execute Module D full scoring across all 8 metrics. Create Health Snapshots DB row with component scores. Calculate MoM change vs previous snapshot. Send comprehensive report via Google Chat.

### H8. Biomarker Trend Report
- **Schedule**: Triggered when new labs entered (not scheduled — fires on Lab Results DB update)
- **Model**: Gemini 2.5 Flash
- **Action**: Execute Module C trend analysis for all markers with ≥3 data points. Generate priority actions for out-of-range markers. Send report via Google Chat.

### H9. Family Health Calendar
- **Schedule**: Monday 8:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Run Module H weekly scan. Query Family Health Calendar DB for overdue, due-soon, and upcoming events. Alert via Telegram. Include scheduling links if provider info is available.

### H10. Supplement Schedule
- **Schedule**: Daily 7:00 AM / 9:00 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Send morning and evening supplement reminders based on Medications DB + `supplement_timing.json`. Include each supplement name, dosage, and any special instructions (e.g., "take with fatty meal", "take on empty stomach"). Mark as 'reminded' in Medications DB.

---

## Cron Summary (All 10 Health Jobs)

| # | Job | Schedule | Skill |
|---|-----|----------|-------|
| H1 | Hevy Workout Sync | Daily 10:00 PM | health-automation |
| H2 | Body Metrics Sync | Sat 8:00 AM | health-automation |
| H3 | Weekly Training Summary | Sun 7:00 PM | health-automation |
| H4 | Supplement Reorder Alert | Wed 9:00 AM | health-automation |
| H5 | Recovery Score | Daily 7:00 AM | **health-planner** |
| H6 | Training Intelligence | Sun 7:15 PM | **health-planner** |
| H7 | Composite Health Score | 1st 8:30 PM | **health-planner** |
| H8 | Biomarker Trend Report | On new labs | **health-planner** |
| H9 | Family Health Calendar | Mon 8:00 AM | **health-planner** |
| H10 | Supplement Schedule | Daily 7am/9pm | **health-planner** |

---

## Integration with health-automation

This skill **reads from** but never **writes to** the databases owned by `health-automation`:

| Database | Owner | This Skill's Access |
|----------|-------|---------------------|
| 🏋️ Workouts | health-automation | READ — exercise history for plateau detection, volume tracking |
| 🏆 PRs | health-automation | READ — personal records for progressive overload analysis |
| 📏 Body Metrics | health-automation | READ — weight/BF% for body composition scoring, meal planning |
| 💊 Medications | health-automation | READ — supplement adherence, timing data |
| 🧪 Lab Results | health-automation | READ — biomarker values for trend analysis |
| 🔬 Lab Markers | health-automation | READ — reference ranges and optimal targets |
| 🩹 Injuries | **health-planner** | READ/WRITE — injury tracking and restriction management |
| 👨‍👩‍👦 Family Health Calendar | **health-planner** | READ/WRITE — appointment scheduling and reminders |
| 📸 Health Snapshots | **health-planner** | READ/WRITE — monthly composite score history |

### Shared Data

- **Exercise templates**: Both skills reference `exercise_templates.json` from health-automation for exercise metadata and muscle group mapping.
- **Health data**: Both skills read from `health_data.db` (Apple Health via Health Auto Export). health-automation manages the sync; this skill reads for recovery/sleep scoring.
- **Supplement timing**: Both skills use `supplement_timing.json`. health-automation manages inventory; this skill handles daily reminders.

---

## Resource Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `resources/health_score_weights.json` | Composite Health Score metric definitions, weights, and scoring thresholds |
| `resources/exercise_library.json` | Exercise form cues, technique tips, and warmup recommendations (40+ exercises) |
