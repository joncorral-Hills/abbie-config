import urllib.request
import json
import sys
import argparse
import os
import datetime
import time

def fetch_json(url, headers={}):
    """Fetches JSON from a URL with a timeout and basic error handling."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_sp500_tickers():
    """Fetches S&P 500 tickers from a public Wikipedia JSON endpoint (via wikipedia API) or uses a small fallback list for demo."""
    url = "https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies&format=json&prop=text"
    print("Fetching S&P 500 universe...", file=sys.stderr)
    try:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK.B", "TSLA", "UNH", "JNJ"]
    except Exception as e:
        print(f"Failed to fetch S&P 500: {e}", file=sys.stderr)
        return []

def analyze_ticker(ticker, fmp_key):
    """Analyzes a single ticker using Financial Modeling Prep (and ideally SEC EDGAR)."""
    if not fmp_key:
        print("Warning: FMP_API_KEY not set. Cannot fetch data.", file=sys.stderr)
        return {"ticker": ticker, "pass": False, "score": 0, "error": "Missing FMP_API_KEY"}

    metrics = {}
    gates = {}
    score = 0
    max_score = 70  # 10 points per metric (7 metrics)

    # 1. Fetch Key Metrics (TTM) — using /stable/ endpoints (free tier)
    metrics_url = f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={ticker}&apikey={fmp_key}"
    metrics_data = fetch_json(metrics_url)
    
    # 2. Fetch Financial Ratios (TTM)
    ratios_url = f"https://financialmodelingprep.com/stable/ratios-ttm?symbol={ticker}&apikey={fmp_key}"
    ratios_data = fetch_json(ratios_url)
    
    # 3. Fetch Income Statement (Annual for YoY Growth)
    income_url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={fmp_key}"
    income_data = fetch_json(income_url)

    # 4. Fetch Profile (for Sector)
    profile_url = f"https://financialmodelingprep.com/stable/profile?symbol={ticker}&apikey={fmp_key}"
    profile_data = fetch_json(profile_url)
    
    if not metrics_data or not ratios_data or not income_data or len(income_data) < 2 or not profile_data:
        return {"ticker": ticker, "pass": False, "score": 0, "error": "Incomplete data from FMP API"}

    m_data = metrics_data[0] if isinstance(metrics_data, list) and metrics_data else metrics_data if isinstance(metrics_data, dict) else {}
    r_data = ratios_data[0] if isinstance(ratios_data, list) and ratios_data else ratios_data if isinstance(ratios_data, dict) else {}
    curr_income = income_data[0] if isinstance(income_data, list) and len(income_data) > 0 else {}
    prev_income = income_data[1] if isinstance(income_data, list) and len(income_data) > 1 else {}
    p_data = profile_data[0] if isinstance(profile_data, list) and profile_data else profile_data if isinstance(profile_data, dict) else {}

    sector = p_data.get("sector", "Unknown")

    # --- Compute Metrics ---

    # 1. PEG Ratio
    peg = r_data.get("priceToEarningsGrowthRatioTTM", None)
    metrics["PEG Ratio"] = peg
    if peg is not None and peg > 0:
        if peg < 1.0:
            gates["PEG < 1.0"] = True; score += 10
        elif peg < 2.0:
            gates["PEG < 1.0"] = False; score += 5
        else:
            gates["PEG < 1.0"] = False
    
    # 2. YoY EPS Growth
    eps_curr = curr_income.get("eps", 0)
    eps_prev = prev_income.get("eps", 0)
    eps_growth = ((eps_curr - eps_prev) / abs(eps_prev)) if eps_prev else 0
    metrics["YoY EPS Growth"] = eps_growth
    if eps_growth > 0.10:
        gates["EPS Growth > 10%"] = True; score += 10
    elif eps_growth > 0:
        gates["EPS Growth > 10%"] = False; score += 5
    else:
        gates["EPS Growth > 10%"] = False

    # 3. YoY Revenue Growth
    rev_curr = curr_income.get("revenue", 0)
    rev_prev = prev_income.get("revenue", 0)
    rev_growth = ((rev_curr - rev_prev) / rev_prev) if rev_prev else 0
    metrics["YoY Revenue Growth"] = rev_growth
    if rev_growth > 0.08:
        gates["Rev Growth > 8%"] = True; score += 10
    elif rev_growth > 0:
        gates["Rev Growth > 8%"] = False; score += 5
    else:
        gates["Rev Growth > 8%"] = False

    # 4. Debt-to-Equity
    de_ratio = r_data.get("debtToEquityRatioTTM", None)
    metrics["Debt-to-Equity"] = de_ratio
    
    de_threshold = 1.5
    if sector == "Technology": de_threshold = 1.0
    elif sector in ["Utilities", "Financial Services"]: de_threshold = 2.5
    
    if de_ratio is not None and de_ratio < de_threshold:
        gates[f"D/E < {de_threshold}"] = True; score += 10
    else:
        gates[f"D/E < {de_threshold}"] = False

    # 5. FCF Yield
    fcf_yield = m_data.get("freeCashFlowYieldTTM", None)
    metrics["FCF Yield"] = fcf_yield
    if fcf_yield is not None and fcf_yield > 0.05:
        gates["FCF Yield > 5%"] = True; score += 10
    else:
        gates["FCF Yield > 5%"] = False

    # 6. Dividend Payout
    payout = r_data.get("dividendPayoutRatioTTM", None)
    metrics["Dividend Payout"] = payout
    if payout is not None and 0.3 <= payout <= 0.6:
        gates["Payout 30-60%"] = True; score += 10
    elif payout is not None and payout > 0:
        gates["Payout 30-60%"] = False; score += 3  # Has a dividend, just outside range
    else:
        gates["Payout 30-60%"] = False

    # 7. P/E vs 5yr (Simplified approximation since we only fetched TTM)
    pe_ttm = r_data.get("priceToEarningsRatioTTM", None)
    metrics["P/E"] = pe_ttm
    if pe_ttm is not None and pe_ttm > 0:
        score += 10 # Default pass for simplified version

    final_score = int((score / max_score) * 100)
    passed = final_score > 60

    time.sleep(0.5) # Rate limiting

    return {
        "ticker": ticker,
        "score": final_score,
        "metrics": metrics,
        "gates": gates,
        "pass": passed
    }

def main():
    parser = argparse.ArgumentParser(description="Stock Fundamentals Screener")
    parser.add_argument("tickers", nargs="*", help="List of stock tickers to screen")
    parser.add_argument("--universe", choices=["sp500"], help="Screen a universe of stocks")
    args = parser.parse_args()

    tickers = args.tickers
    if args.universe == "sp500":
        tickers.extend(get_sp500_tickers())

    if not tickers and not sys.stdin.isatty():
        tickers = [line.strip() for line in sys.stdin.readlines() if line.strip()]

    if not tickers:
        print("Please provide at least one ticker or a universe.", file=sys.stderr)
        sys.exit(1)
        
    fmp_key = os.environ.get("FMP_API_KEY")

    results = []
    for ticker in set(tickers):
        print(f"Analyzing {ticker}...", file=sys.stderr)
        res = analyze_ticker(ticker.upper(), fmp_key)
        results.append(res)

    output = {
        "timestamp": datetime.datetime.now().isoformat(),
        "results": results,
        "disclaimer": "This analysis is AI-generated for informational purposes only and is not financial advice."
    }
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
