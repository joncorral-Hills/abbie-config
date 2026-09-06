#!/usr/bin/env python3
"""
OpenRouter Weekly Spending Report.
Reads usage log, calculates weekly spend, projects burn rate.
"""
import csv, os, sys
from datetime import datetime, timedelta
from collections import defaultdict

LOG_PATH = "/home/ubuntu/memory/openrouter_usage.csv"

def read_log():
    rows = []
    if not os.path.exists(LOG_PATH):
        return rows
    with open(LOG_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["timestamp_dt"] = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                row["remaining"] = float(row["remaining"])
                row["total_usage"] = float(row["total_usage"])
                rows.append(row)
            except Exception:
                continue
    return rows

def get_week_start(dt):
    """Monday-start week."""
    return dt - timedelta(days=dt.weekday())

def generate_report():
    rows = read_log()
    if len(rows) < 2:
        print("Not enough data for a report. Need at least 2 log entries.")
        return None
    
    # Sort by timestamp
    rows.sort(key=lambda r: r["timestamp_dt"])
    
    # Calculate per-entry spend (delta from previous)
    for i in range(1, len(rows)):
        prev_usage = rows[i-1]["total_usage"]
        curr_usage = rows[i]["total_usage"]
        rows[i]["session_spend"] = max(0, curr_usage - prev_usage)
    rows[0]["session_spend"] = 0.0
    
    # Group by week
    weeks = defaultdict(list)
    for row in rows:
        week_key = get_week_start(row["timestamp_dt"]).strftime("%Y-%m-%d")
        weeks[week_key].append(row)
    
    # Current week
    now = datetime.now()
    current_week_start = get_week_start(now)
    current_week_key = current_week_start.strftime("%Y-%m-%d")
    
    # Previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_key = prev_week_start.strftime("%Y-%m-%d")
    
    # Calculate weekly totals
    def week_spend(week_key):
        entries = weeks.get(week_key, [])
        if not entries:
            return 0.0
        # Spend = first entry remaining - last entry remaining
        first_rem = entries[0]["remaining"]
        last_rem = entries[-1]["remaining"]
        return max(0, first_rem - last_rem)
    
    current_week_spend = week_spend(current_week_key)
    prev_week_spend = week_spend(prev_week_key)
    
    # All-time stats
    total_purchased = rows[-1]["total_usage"] + rows[-1]["remaining"]
    total_spent = rows[-1]["total_usage"]
    current_remaining = rows[-1]["remaining"]
    
    # Daily average (current week)
    days_into_week = (now - current_week_start).total_seconds() / 86400
    days_into_week = max(1, days_into_week)
    daily_avg_current = current_week_spend / days_into_week
    
    # Daily average (all time)
    first_entry = rows[0]["timestamp_dt"]
    days_total = (now - first_entry).total_seconds() / 86400
    days_total = max(1, days_total)
    daily_avg_alltime = total_spent / days_total
    
    # Projections
    days_remaining_current = current_remaining / daily_avg_current if daily_avg_current > 0 else float('inf')
    days_remaining_alltime = current_remaining / daily_avg_alltime if daily_avg_alltime > 0 else float('inf')
    
    # Week-over-week change
    wow_change = 0.0
    if prev_week_spend > 0:
        wow_change = ((current_week_spend - prev_week_spend) / prev_week_spend) * 100
    
    # Daily breakdown for current week
    daily_spend = defaultdict(float)
    for row in weeks.get(current_week_key, []):
        day = row["timestamp_dt"].strftime("%a %m/%d")
        daily_spend[day] += row.get("session_spend", 0)
    
    # Build report
    report_lines = [
        "📊 OpenRouter Weekly Spending Report",
        f"Week of {current_week_start.strftime('%b %d, %Y')}",
        "",
        "💰 Balance",
        f"  Remaining:        ${current_remaining:.2f}",
        f"  Total purchased:  ${total_purchased:.2f}",
        f"  Total spent:      ${total_spent:.2f}",
        "",
        "📈 This Week",
        f"  Spent:            ${current_week_spend:.2f}",
        f"  Daily average:    ${daily_avg_current:.2f}",
    ]
    
    if prev_week_spend > 0:
        arrow = "📈" if wow_change > 0 else "📉"
        report_lines.append(f"  vs last week:     {arrow} {abs(wow_change):.1f}%")
    else:
        report_lines.append("  vs last week:     N/A (no data)")
    
    report_lines.extend([
        "",
        "📅 Daily Breakdown (This Week)",
    ])
    
    for day in sorted(daily_spend.keys()):
        spend = daily_spend[day]
        bar = "█" * int(spend * 20)  # rough viz
        report_lines.append(f"  {day}:  ${spend:.2f}  {bar}")
    
    run_out_date = 'N/A (no spend)' if days_remaining_current == float('inf') else (now + timedelta(days=days_remaining_current)).strftime('%b %d, %Y')
    report_lines.extend([
        "",
        "🔮 Projections",
        f"  Burn rate (this week):  ${daily_avg_current:.2f}/day",
        f"  Burn rate (all time):   ${daily_avg_alltime:.2f}/day",
        f"  Days left (this week):  {days_remaining_current:.0f}",
        f"  Days left (all time):   {days_remaining_alltime:.0f}",
        f"  Run out date (weekly):  {run_out_date}",
    ])
    
    # Alerts
    report_lines.append("")
    if current_remaining < 5:
        report_lines.append("⚠️  ALERT: Less than $5 remaining. Top up soon.")
    elif current_remaining < 10:
        report_lines.append("⚡ Note: Under $10 remaining.")
    else:
        report_lines.append("✅ Balance healthy.")
    
    report = "\n".join(report_lines)
    return report

def main():
    report = generate_report()
    if report:
        print(report)
        # Also save to file
        report_path = "/home/ubuntu/memory/openrouter_weekly_report.txt"
        with open(report_path, "w") as f:
            f.write(report + "\n")
        print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
