---
name: life-score
description: >
  Composite Life Score (0–100) that unifies all domain health scores into a single household wellness metric. Reads Financial Health Score from financial-planner, Composite Health Score from health-planner, and self-calculates a Growth Score. Business and Career scores are placeholder-ready for future skills. Provides monthly trend tracking and identifies the highest-impact area to focus on.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Life Score (life-score)

## Overview

The `life-score` skill serves as Allie's executive summary module, computing a Composite Life Score (0–100). It reads key metrics from active domain-specific skills and unifies them into a single holistic wellness indicator for the household. It self-calculates a Growth Score and provides placeholders for Business and Career scores. Monthly trends are tracked, and actionable recommendations are generated based on the highest-impact areas for improvement.

### Architecture

```ascii
                      +-------------------+
                      |   life-score      |
                      |   (Meta-Skill)    |
                      +---------+---------+
                                |
        +-----------------------+-----------------------+
        |                       |                       |
+-------v-------+       +-------v-------+       +-------v-------+
|  financial-   |       |    health-    |       |   Self-Calc   |
|   planner     |       |    planner    |       |   (Growth)    |
+---------------+       +---------------+       +---------------+
| Net Worth     |       | Health        |       | Books, Skills,|
| Snapshots DB  |       | Snapshots DB  |       | Courses       |
+---------------+       +---------------+       +---------------+
```

---

## Setup (One-Time)

### 1. Create DASHBOARD Page
Create a new Notion page named **DASHBOARD** at the root level alongside FINANCE and Health & Fitness. This will host high-level metrics.

### 2. Create Notion Database: `📊 Life Snapshots`
Create this inline database under the DASHBOARD page.

| Property | Type | Details |
| :--- | :--- | :--- |
| `Month` | Title | Format: YYYY-MM |
| `Life Score` | Number | 0-100 format |
| `Financial Score` | Number | 0-100 format |
| `Health Score` | Number | 0-100 format |
| `Business Score` | Number | 0-100 format |
| `Career Score` | Number | 0-100 format |
| `Growth Score` | Number | 0-100 format |
| `MoM Change` | Number | Signed number showing change from previous month |
| `Trend` | Select | Options: `Rising`, `Stable`, `Declining` |
| `Top Win` | Rich Text | Best performing or most improved domain |
| `Top Focus` | Rich Text | Lowest scoring / highest potential impact area |
| `Notes` | Rich Text | AI-generated summary or user comments |

---

## Modules

### Module A: Score Normalization and Weighting

**Purpose**: Compute the weighted Composite Life Score, handling inactive domains gracefully by redistributing weights.

**Data Sources**:
- `financial-planner`: Financial Health Score from Net Worth Snapshots DB.
- `health-planner`: Composite Health Score from Health Snapshots DB.
- Module B: Calculated Growth Score.

**Target Weights**:
- Financial: 0.25
- Health: 0.25
- Business: 0.20 (Placeholder, initially 0)
- Career: 0.15 (Placeholder, initially fixed at 50)
- Growth: 0.15

**Algorithm**:
```python
def calculate_composite_score(scores, active_domains):
    target_weights = {
        'financial': 0.25,
        'health': 0.25,
        'business': 0.20,
        'career': 0.15,
        'growth': 0.15
    }
    
    # Calculate total weight of active domains
    total_active_weight = sum(target_weights[domain] for domain in active_domains)
    
    # Redistribute weights proportionally
    actual_weights = {
        domain: (target_weights[domain] / total_active_weight)
        for domain in active_domains
    }
    
    composite_score = 0
    for domain in active_domains:
        composite_score += scores[domain] * actual_weights[domain]
        
    return composite_score, actual_weights
```

**Output**: A finalized Composite Life Score (0-100).

### Module B: Growth Score Calculation

**Purpose**: Calculate the domain score for personal growth and learning based on trackable inputs.

**Data Sources**: Automated from existing Allie systems — Invention Ideas DB, Skill modifications, Workout consistency (health-planner), and Project Board completions.

**Algorithm**:
```python
def calculate_growth_score():
    # 1. Invention activity (from INVENT Notion DB)
    #    DB: 52b3ad05-9b6a-431a-b994-de8b79cb16ea
    inventions_this_month = count_notion_pages(
        db_id="52b3ad05-9b6a-431a-b994-de8b79cb16ea",
        filter={"Date": {"this_month": True}}
    )
    invention_score = min(100, inventions_this_month * 50)  # 2 ideas = max
    
    # 2. Skill evolution (count new/refined skills this month)
    #    Source: Hermes skill directory or Notion SKILLS DB
    skills_modified = count_skills_modified_this_month()
    skill_score = min(100, skills_modified * 25)  # 4 skills = max
    
    # 3. Workout consistency as discipline proxy (from health-planner)
    #    DB: Health & Fitness page workouts
    workouts_this_month = count_notion_pages(
        db_id=WORKOUTS_DB_ID,
        filter={"Date": {"this_month": True}}
    )
    consistency_score = min(100, (workouts_this_month / 12) * 100)  # 3/week = max
    
    # 4. Project completion (from Project Board)
    #    DB: 39563d55-66c5-81c3-827b-e124fc4bba17
    projects_completed = count_notion_pages(
        db_id="39563d55-66c5-81c3-827b-e124fc4bba17",
        filter={"Status": "Done", "Completed": {"this_month": True}}
    )
    project_score = min(100, projects_completed * 33)  # 3 completions = max
    
    return (invention_score + skill_score + consistency_score + project_score) / 4
```

**Output**: A Growth Score (0-100).

### Module C: Trend & Action Engine

**Purpose**: Analyze the 3-month rolling trend and determine actionable recommendations based on weight and score differentials.

**Algorithm**:
```python
def analyze_trend_and_focus(history, current_scores, weights):
    # Trend Analysis
    if len(history) >= 2:
        diffs = [history[i] - history[i-1] for i in range(1, len(history))]
        diffs.append(current_scores['composite'] - history[-1])
        
        if all(d >= 0 for d in diffs[-3:]):
            trend = "Rising"
        elif all(d <= 0 for d in diffs[-3:]):
            trend = "Declining"
        else:
            trend = "Stable"
    else:
        trend = "Stable"

    # Focus Area Analysis (Lowest Score * Highest Weight = Biggest Impact)
    improvement_potentials = {
        domain: (100 - current_scores[domain]) * weights[domain]
        for domain in current_scores if domain != 'composite'
    }
    top_focus = max(improvement_potentials, key=improvement_potentials.get)
    
    return trend, top_focus
```

---

## Cron Automations

### 1. LS1: Monthly Life Score Report
- **Schedule**: 3rd of the month at 9:00 PM CT (Ensures financial and health scores have updated on the 1st and 2nd).
- **Model**: DeepSeek V4 Flash
- **Action**: 
  1. Retrieve latest Financial Health Score and Composite Health Score.
  2. Compute Growth Score.
  3. Calculate the Composite Life Score with active weights (e.g., Financial: 0.385, Health: 0.385, Growth: 0.230).
  4. Determine 3-month trend, highest contribution (Top Win), and lowest weighted score (Top Focus).
  5. Check milestone alerts.
  6. Create a row in `📊 Life Snapshots`.
  7. Send Telegram report.
- **Message Format (Telegram)**:
  ```
  📊 Monthly Life Score: {YYYY-MM}
  
  🏆 Composite Score: {score} ({emoji}) | MoM: {change}
  📈 Trend: {trend}
  
  Domain Breakdown:
  • 💰 Financial: {fin_score} (Weight: {fin_weight}%)
  • 🏃‍♂️ Health: {health_score} (Weight: {health_weight}%)
  • 🌱 Growth: {growth_score} (Weight: {growth_weight}%)
  
  🌟 Top Win: {top_win_domain} driving positive impact.
  🎯 Top Focus: {top_focus_domain} presents the highest improvement potential.
  
  💡 Recommendation: {actionable_advice_based_on_focus}
  ```

- **Structured Output**: In addition to the Telegram message, write a machine-readable JSON file for downstream skill consumption.
  - **Path**: `~/.hermes/cron_outputs/ls1_latest.json`
  - **Schema**:
    ```json
    {
      "month": "YYYY-MM",
      "composite_score": 0-100,
      "domain_scores": {
        "financial": 0-100,
        "health": 0-100,
        "growth": 0-100,
        "business": 0-100,
        "career": 0-100
      },
      "weights": {
        "financial": 0.0-1.0,
        "health": 0.0-1.0,
        "growth": 0.0-1.0
      },
      "trend": "Rising|Stable|Declining",
      "mom_change": -100 to 100,
      "top_win": "domain name",
      "top_focus": "domain name",
      "milestones": ["milestone strings if triggered"],
      "timestamp": "ISO8601"
    }
    ```
  - **Write**: After sending the Telegram message, write this JSON file. Overwrite any existing file at that path.
  - **Consumers**: `financial-planner` (reads composite for cross-reference), future dashboard skills.

---

## Interpretation Guidelines

| Range | Rating | Emoji |
|-------|--------|-------|
| 90-100 | Thriving | 🏆 |
| 75-89 | Strong | ✅ |
| 60-74 | Building | ⚠️ |
| 40-59 | Needs Attention | 🔶 |
| 0-39 | Critical | 🚨 |

---

## Milestone Alerts

The engine monitors for the following events and issues specific alerts when triggered:
- **First 80+**: "🎉 Milestone unlocked! Life Score crossed 80 for the first time."
- **Momentum**: "🔥 Momentum! Life Score has increased for 3 consecutive months."
- **Breakthrough**: "🚀 Breakthrough! {Domain} crossed from below 50 to above 70."
- **Intervention**: "🚨 Warning: Life Score has dropped below 50. Initiating strategic review."

---

## Resource Files

| File | Purpose |
| :--- | :--- |
| `prompts/monthly_report.txt` | Prompt for formatting the Monthly Life Score report and actionable advice. |
| `config.json` | Configuration mapping weights, milestones, and Notion DB IDs. |

---

## Integration

| Domain/Skill | READ | WRITE |
| :--- | :--- | :--- |
| `financial-planner` | `Net Worth Snapshots` (Financial Health Score) | None |
| `health-planner` | `Health Snapshots` (Composite Health Score) | None |
| `project-board` | `📋 Project Board` (completed projects count) | None |
| `life-score` | Self (DASHBOARD metrics), INVENT DB (ideas count), Project Board (completions) | `📊 Life Snapshots` |

---

## Data Collection Checklist

Growth Score inputs are now **fully automated** from existing Notion databases:
1. [x] Invention ideas — auto-read from INVENT DB (`52b3ad05`)
2. [x] Skill modifications — counted from Hermes skill directory
3. [x] Workout consistency — auto-read from Health & Fitness Workouts DB
4. [x] Project completions — auto-read from Project Board (`39563d55`)
5. [ ] Links to DASHBOARD and `📊 Life Snapshots` Notion pages once created.
