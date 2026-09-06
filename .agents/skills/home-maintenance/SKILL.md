---
name: home-maintenance
description: >
  Seasonal and recurring home maintenance calendar with automated reminders. Generates task schedules based on Kansas City metro climate zone (6a). Tracks maintenance history, vendor contacts, and estimated costs. Prevents expensive repairs through proactive scheduling.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Home Maintenance (HM)

## 1. Overview

This is a standalone tactical skill that provides a seasonal home maintenance calendar auto-generated for the Kansas City metro area (USDA Zone 6a / IECC Zone 4A). It proactively surfaces upcoming and overdue maintenance tasks to prevent expensive property damage, tracks maintenance history and estimated costs, and manages preferred vendor contacts.

```ascii
+-----------------------+      +-------------------+      +------------------+
| Notion DB:            |      | Allie HM Skill    |      | Telegram / GChat |
| 🏠 Home Maintenance    |<---->| (Cron HM1, HM2)   |----->| Alerts & Reports |
| (Tasks, Dates, Costs) |      | (Python Logic)    |      | (Reminders)      |
+-----------------------+      +-------------------+      +------------------+
       |                               ^
       v                               |
+-----------------------+              |
| Resources (JSON):     |--------------+
| - Schedule            |
| - Vendors             |
+-----------------------+
```

## 2. Setup (One-Time)

### Create 🏠 Home Maintenance Database
Create this inline database under a new **HOME** page in Notion (sibling to FINANCE and Health & Fitness).

| Property       | Type            | Details |
| -------------- | --------------- | ------- |
| Task           | Title           | e.g., 'Replace HVAC filter' |
| Category       | Select          | Options: `HVAC`, `Plumbing`, `Exterior`, `Lawn & Landscape`, `Pest Control`, `Appliances`, `Safety`, `Seasonal` |
| Frequency      | Select          | Options: `Monthly`, `Quarterly`, `Semi-Annual`, `Annual`, `Seasonal-Spring`, `Seasonal-Summer`, `Seasonal-Fall`, `Seasonal-Winter` |
| Last Completed | Date            | When last done |
| Next Due       | Formula         | Calculated from Last Completed + Frequency |
| Estimated Cost | Number (dollar) | Average cost (DIY vs pro) |
| Priority       | Select          | Options: `Critical` (structural/safety), `Important` (prevents damage), `Nice-to-Have` |
| Status         | Select          | Options: `Upcoming`, `Due`, `Overdue`, `Completed`, `Skipped` |
| DIY?           | Checkbox        | Whether Jon can do it himself |
| Vendor         | Rich Text       | Preferred contractor/service |
| Notes          | Rich Text       | Special instructions, product model numbers |

## 3. Modules

### Module A: Maintenance Task Evaluation (Core Logic)
**Purpose**: Evaluate the Notion database against the current date to determine upcoming, due, and overdue tasks.
**Data Sources**: `🏠 Home Maintenance` Notion DB.
**Algorithm**:
```python
import datetime

def evaluate_maintenance_tasks(notion_tasks):
    today = datetime.date.today()
    target_date = today + datetime.timedelta(days=7)
    
    actionable_tasks = []
    
    for task in notion_tasks:
        if task['Status'] == 'Completed' or task['Status'] == 'Skipped':
            continue
            
        next_due = parse_date(task['Next Due'])
        if not next_due:
            continue
            
        if next_due < today:
            task['Calculated Status'] = 'Overdue'
            actionable_tasks.append(task)
        elif today <= next_due <= target_date:
            task['Calculated Status'] = 'Due'
            actionable_tasks.append(task)
            
    # Sort by priority, then date
    priority_order = {'Critical': 0, 'Important': 1, 'Nice-to-Have': 2}
    actionable_tasks.sort(key=lambda x: (priority_order.get(x['Priority'], 3), parse_date(x['Next Due'])))
    
    return actionable_tasks
```
**Output**: List of actionable task objects sorted by priority.

### Module B: Seasonal Seeder
**Purpose**: Seeds the Notion DB with Kansas City (Zone 6a) specific tasks if they do not exist.
**Data Sources**: `maintenance_schedule.json`.
**Algorithm**:
```python
import json

def seed_seasonal_tasks(notion_client, db_id, schedule_path):
    with open(schedule_path, 'r') as f:
        schedule = json.load(f)
        
    existing_tasks = get_all_tasks_from_notion(notion_client, db_id)
    existing_task_names = {t['Task'] for t in existing_tasks}
    
    for task in schedule:
        if task['name'] not in existing_task_names:
            create_notion_task(notion_client, db_id, task)
```
**Output**: Notion DB populated with core maintenance tasks.

## 4. Cron Automations

### Cron HM1: Weekly Maintenance Check
- **Schedule**: Weekly on Monday at 8:00 AM CT
- **Model**: Gemini 3 Flash
- **Action**: Queries `🏠 Home Maintenance` for tasks where `Next Due <= today + 7 days`.
- **Message Format** (Telegram):
  ```
  🛠️ **Weekly Home Maintenance**
  
  🚨 **Overdue**:
  - Test Sump Pump (Critical)
  
  ⚠️ **Due this week**:
  - Replace HVAC Filter (HVAC) - DIY
  
  _Have you completed any of these? Reply with "Done [Task]" to update Notion._
  ```

### Cron HM2: Seasonal Prep Reminder
- **Schedule**: Quarterly on the 1st of March, June, September, December at 9:00 AM CT
- **Model**: Kimi K2.6 (for aggregating and parsing seasonal tasks and vendor contexts)
- **Action**: Queries all tasks associated with the upcoming season and checks vendor readiness.
- **Message Format** (Telegram):
  ```
  🍂 **Fall Maintenance Prep (Zone 6a)**
  
  It's time to prep the house for Fall/Winter!
  
  **Key Tasks:**
  - Furnace tune-up (Important) - Pro ~$150 (Vendor: Kansas City HVAC Services)
  - Gutter clean (Important) - DIY or Pro ~$200
  - Winterize sprinklers (Important) - Pro ~$75
  
  _Shall I reach out to any vendors for quotes, or will you DIY?_
  ```

## 5. Resource Files

| File | Description |
| ---- | ----------- |
| `maintenance_schedule.json` | Comprehensive list of 30+ maintenance tasks for Zone 6a, categorized with cost and priority data. |
| `vendors.json` | Template for tracking preferred local vendors (HVAC, Plumbing, etc.) |

## 6. Integration

- **Read**: `maintenance_schedule.json`, `vendors.json`, `🏠 Home Maintenance` Notion DB.
- **Write**: `🏠 Home Maintenance` Notion DB (updates statuses, next due dates, vendor assignments based on user confirmation).

## 7. Data Collection Checklist

Information needed from Jon to fully operationalize this skill:
- [ ] Confirm Notion page setup and provide the database ID for the `🏠 Home Maintenance` DB.
- [ ] Fill out the `vendors.json` file with preferred contractor contact information (if known).
- [ ] Provide initial dates for "Last Completed" for major tasks (e.g., when was the last HVAC tune-up?).
- [ ] Confirm preferences for DIY vs. Pro for tasks like gutter cleaning and power washing.
