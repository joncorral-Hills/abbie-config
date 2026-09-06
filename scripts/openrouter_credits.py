#!/usr/bin/env python3
"""
OpenRouter credit tracker.
Check balance, log usage, alert on low credits.
"""
import urllib.request, json, os, sys
from datetime import datetime

ENV_PATH = "/home/ubuntu/.hermes/.env"
LOG_PATH = "/home/ubuntu/memory/openrouter_usage.csv"

def get_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k] = v
    return env

def fetch_credits(api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits", headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data.get("data", {})

def fetch_key_info(api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data.get("data", {})

def log_usage(total_credits, total_usage):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    remaining = total_credits - total_usage
    line = f"{now},{total_credits:.6f},{total_usage:.6f},{remaining:.6f}\n"
    # Append or create with header
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w") as f:
            f.write("timestamp,total_credits,total_usage,remaining\n")
    with open(LOG_PATH, "a") as f:
        f.write(line)
    return remaining

def parse_rate(rate):
    """Parse model price from OpenRouter model JSON."""
    # Format: "$0.00000005" or 5e-08
    if isinstance(rate, str):
        return float(rate.replace("$", "").replace(",", ""))
    return float(rate) if rate else 0

def estimate_cost(prompt_tokens, completion_tokens, model="kimi-k2.6"):
    """Rough cost estimate per 1K tokens. Does not call API."""
    # Prices as of mid-2026 (fallback if API unavailable)
    RATES = {
        "kimi-k2.6": (0.80, 2.00),  # input, output per 1M tokens
        "gemini-3-flash": (0.10, 0.40),
        "gemini-3-pro": (1.25, 10.00),
        "claude-sonnet-4": (3.00, 15.00),
        "default": (1.00, 3.00),
    }
    rate = RATES.get(model.lower().replace("-", "").replace("/", ""), RATES["default"])
    in_cost = (prompt_tokens / 1_000_000) * rate[0]
    out_cost = (completion_tokens / 1_000_000) * rate[1]
    return in_cost + out_cost

def main():
    env = get_env()
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not found in .env")
        sys.exit(1)
    
    credits = fetch_credits(api_key)
    key_info = fetch_key_info(api_key)
    
    total = credits.get("total_credits", 0)
    used = credits.get("total_usage", 0)
    remaining = total - used
    
    # Log it
    log_usage(total, used)
    
    # Check usage from this session (compare to last log entry)
    prev_remaining = None
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("timestamp,")]
            if len(lines) > 1:
                prev = lines[-2].split(",")
                if len(prev) >= 4:
                    prev_remaining = float(prev[3])
    
    session_cost = prev_remaining - remaining if prev_remaining else 0
    
    print(f"""
OpenRouter Credit Status
========================
Total purchased:    ${total:.2f}
Total used:         ${used:.2f}
Remaining:          ${remaining:.2f}

Usage breakdown
---------------
This session:       ${max(0, session_cost):.4f}
Today's usage:      ${key_info.get('usage_daily', 0):.4f}
This week:          ${key_info.get('usage_weekly', 0):.4f}
This month:         ${key_info.get('usage_monthly', 0):.4f}

Low credit warnings
-------------------
If credits drop below thresholds, add alerts here.
Current: ${remaining:.2f} remaining
""")
    
    if remaining < 6.0:
        print(f"🚨 LOW CREDIT ALERT: ${remaining:.2f} remaining — below $6 threshold. Top up now.")
    elif remaining < 10.0:
        print(f"⚠️  WARNING: ${remaining:.2f} remaining. Consider topping up soon.")
    if remaining < 1.0:
        print("🚨 CRITICAL: Less than $1 remaining. Top up immediately or jobs will fail.")
    
    return remaining

if __name__ == "__main__":
    main()
