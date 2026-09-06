#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

FRED_API_KEY = os.environ.get("FRED_API_KEY")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY")

def fetch_fred_series(series_id):
    if not FRED_API_KEY:
        return None
    
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=12"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if 'observations' in data and len(data['observations']) > 0:
                for obs in data['observations']:
                    if obs['value'] != '.':
                        return float(obs['value'])
    except Exception as e:
        print(f"Error fetching FRED series {series_id}: {e}", file=sys.stderr)
    return None

def fetch_alpha_vantage_prices(symbol):
    if not ALPHA_VANTAGE_API_KEY:
        return []
    
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            time_series = data.get("Monthly Adjusted Time Series", {})
            
            sorted_dates = sorted(time_series.keys(), reverse=True)
            
            prices = []
            for date in sorted_dates[:4]:
                prices.append(float(time_series[date]["5. adjusted close"]))
            return prices
    except Exception as e:
        print(f"Error fetching Alpha Vantage data for {symbol}: {e}", file=sys.stderr)
    return []

def main():
    disclaimer = "This is AI-generated analysis for informational purposes only and not financial advice."
    
    # 1. Fetch Economic Data
    gdp_growth = fetch_fred_series("A191RL1Q225SBEA")
    unemployment = fetch_fred_series("UNRATE")
    cpi = fetch_fred_series("CPIAUCSL")
    fed_rate = fetch_fred_series("FEDFUNDS")
    yield_curve = fetch_fred_series("T10Y2Y")
    
    economic = {
        "gdp_growth": gdp_growth,
        "unemployment": unemployment,
        "cpi": cpi,
        "fed_rate": fed_rate,
        "yield_curve": yield_curve
    }
    
    # 2. Determine Market Phase
    phase = "Unknown"
    guardrails = []
    
    if gdp_growth is not None and yield_curve is not None and unemployment is not None:
        if gdp_growth < 0 or unemployment > 5.0:
            phase = "Recession"
            guardrails.append("High risk environment. Focus on defensive sectors.")
        elif yield_curve < 0:
            phase = "Late Cycle"
            guardrails.append("Yield curve is inverted, signaling potential recession. Reduce early cycle exposure.")
        elif fed_rate is not None and fed_rate > 3.0 and gdp_growth > 0:
            phase = "Mid Cycle"
            guardrails.append("Rates are elevated. Focus on quality and sectors with pricing power.")
        elif yield_curve > 1.0:
            phase = "Early Cycle"
            guardrails.append("Steep yield curve and economic recovery. Risk-on sectors favored.")
    
    # 3. Fetch Sector Data
    sectors = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLRE", "XLU", "XLB"]
    
    if not ALPHA_VANTAGE_API_KEY:
        sector_rankings = [{"symbol": s, "rs_1m": 0.0, "rs_3m": 0.0} for s in sectors]
        favored_sectors = []
        avoid_sectors = []
    else:
        spy_prices = fetch_alpha_vantage_prices("SPY")
        spy_1m_ret = (spy_prices[0] / spy_prices[1] - 1) if len(spy_prices) >= 2 else 0
        spy_3m_ret = (spy_prices[0] / spy_prices[3] - 1) if len(spy_prices) >= 4 else 0
        
        sector_rankings = []
        for s in sectors:
            prices = fetch_alpha_vantage_prices(s)
            
            rs_1m = 0
            rs_3m = 0
            
            if len(prices) >= 2 and len(spy_prices) >= 2:
                s_1m_ret = prices[0] / prices[1] - 1
                rs_1m = s_1m_ret - spy_1m_ret
                
            if len(prices) >= 4 and len(spy_prices) >= 4:
                s_3m_ret = prices[0] / prices[3] - 1
                rs_3m = s_3m_ret - spy_3m_ret
                
            sector_rankings.append({
                "symbol": s,
                "rs_1m": round(rs_1m * 100, 2),
                "rs_3m": round(rs_3m * 100, 2)
            })
            
        sector_rankings.sort(key=lambda x: (x["rs_3m"], x["rs_1m"]), reverse=True)
        
        favored_sectors = [s["symbol"] for s in sector_rankings if s["rs_3m"] > 0 and s["rs_1m"] > 0]
        avoid_sectors = [s["symbol"] for s in sector_rankings if s["rs_3m"] < 0 and s["rs_1m"] < 0]

    output = {
        "timestamp": datetime.now().isoformat(),
        "economic": economic,
        "market_phase": phase,
        "sector_rankings": sector_rankings,
        "favored_sectors": favored_sectors,
        "avoid_sectors": avoid_sectors,
        "guardrails": guardrails,
        "disclaimer": disclaimer
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
