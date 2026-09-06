import argparse
import json
import os
import subprocess
import sys
import datetime
from pathlib import Path

# ⚠️ UPDATE THIS PATH to match Allie's skills directory on the VM
SKILLS_DIR = Path("/path/to/skills")  # e.g., Path("/home/allie/.gemini/config/skills")

MACRO_SCRIPT = SKILLS_DIR / "stock-market-macro" / "scripts" / "macro_dashboard.py"
FUNDAMENTAL_SCRIPT = SKILLS_DIR / "stock-fundamentals" / "scripts" / "fundamental_screen.py"
TECHNICAL_SCRIPT = SKILLS_DIR / "stock-technicals" / "scripts" / "technical_scan.py"
SENTIMENT_SCRIPT = SKILLS_DIR / "stock-sentiment" / "scripts" / "sentiment_scan.py"

def run_script(script_path, args, env=None):
    """Run a python script via subprocess and parse JSON output."""
    if not script_path.exists():
        print(f"Warning: Script {script_path} not found.", file=sys.stderr)
        return None
    
    cmd = [sys.executable, str(script_path)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env or os.environ,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_path}: {e.stderr}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Error parsing JSON from {script_path}. Output: {result.stdout}", file=sys.stderr)
        return None

def fetch_universe(universe_type, tickers=None):
    """Mock fetch for ticker universe."""
    if universe_type == 'custom' and tickers:
        return [t.strip().upper() for t in tickers.split(',')]
    elif universe_type == 'nasdaq100':
        return ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA']
    else:
        return ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'BRK.B', 'UNH', 'JNJ', 'JPM', 'V']

def calculate_position_sizing(portfolio_size, risk_pct, atr, entry_price):
    """Calculate position size based on risk rules."""
    risk_amount = portfolio_size * risk_pct
    stop_loss_distance = 2 * atr
    if stop_loss_distance <= 0:
        return 0
    shares = risk_amount / stop_loss_distance
    return int(shares)

def main():
    parser = argparse.ArgumentParser(description="Run the weekly stock briefing pipeline.")
    parser.add_argument("--universe", choices=["sp500", "nasdaq100", "custom"], default="sp500")
    parser.add_argument("--tickers", help="Comma-separated list of tickers for custom universe")
    parser.add_argument("--portfolio-size", type=float, default=10000.0)
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--output", help="Output file path (defaults to stdout)")
    args = parser.parse_args()

    universe = fetch_universe(args.universe, args.tickers)

    # 1. Macro Scan
    macro_data = run_script(MACRO_SCRIPT, [])
    favored_sectors = macro_data.get('favored_sectors', ['Technology', 'Healthcare']) if macro_data else ['Technology']
    market_phase = macro_data.get('market_phase', 'Expansion') if macro_data else 'Neutral'

    # 2. Fundamental Screen
    fundamental_data = run_script(FUNDAMENTAL_SCRIPT, universe)
    passed_fundamentals = []
    watchlist = []
    
    if fundamental_data and 'results' in fundamental_data:
        for item in fundamental_data['results']:
            if item.get('score', 0) > 70:
                passed_fundamentals.append(item['ticker'])
            elif item.get('score', 0) > 50:
                watchlist.append(item['ticker'])
    else:
        passed_fundamentals = universe[:5]

    # 3. Technical Scan
    technical_data = []
    if passed_fundamentals:
        tech_res = run_script(TECHNICAL_SCRIPT, passed_fundamentals)
        if tech_res and 'results' in tech_res:
            technical_data = tech_res['results']
    
    # 4. Sentiment Check
    sentiment_data = {}
    for item in technical_data:
        ticker = item.get('ticker')
        if ticker:
            sent_res = run_script(SENTIMENT_SCRIPT, [ticker])
            if sent_res and 'results' in sent_res:
                sentiment_data[ticker] = sent_res['results'][0]

    # 5. Compile Results & Risk Rules
    picks = []
    for tech in technical_data:
        ticker = tech.get('ticker', 'UNK')
        sent = sentiment_data.get(ticker, {})
        
        # Composite score: fundamentals 40% + technicals 30% + sentiment 20% + macro 10%
        fund_score = 70  # default for passed fundamentals
        tech_score = tech.get('score', 50)
        sent_score = sent.get('sentiment_score', 50)
        macro_score = 60  # default
        
        comp_score = int(fund_score * 0.4 + tech_score * 0.3 + sent_score * 0.2 + macro_score * 0.1)
        
        price = tech.get('price', 0)
        atr = price * 0.02  # Approximate ATR as 2% of price
        
        shares = calculate_position_sizing(args.portfolio_size, args.risk_pct, atr, price)
        stop_loss = price - (2 * atr)
        target = price + (5 * atr)
        rr = (target - price) / (price - stop_loss) if (price - stop_loss) != 0 else 0
        
        picks.append({
            'ticker': ticker,
            'score': comp_score,
            'entry': price,
            'stop': round(stop_loss, 2),
            'target': round(target, 2),
            'rr': round(rr, 1),
            'shares': shares,
            'tech_signals': tech.get('signals', {}),
            'sentiment': sent.get('sentiment_score', 'N/A')
        })

    picks.sort(key=lambda x: x['score'], reverse=True)

    # 6. Generate Report
    report = []
    report.append(f"# Weekly Stock Briefing - {datetime.date.today()}")
    report.append(f"\n## Market Conditions")
    report.append(f"**Market Phase**: {market_phase}")
    report.append(f"**Favored Sectors**: {', '.join(str(s) for s in favored_sectors)}")
    
    report.append(f"\n## Top Stock Suggestions")
    report.append("| Rank | Ticker | Score | Entry | Stop | Target | R:R | Shares | Sentiment |")
    report.append("|---|---|---|---|---|---|---|---|---|")
    for i, pick in enumerate(picks[:10], 1):
        report.append(f"| {i} | {pick['ticker']} | {pick['score']} | ${pick['entry']:.2f} | ${pick['stop']:.2f} | ${pick['target']:.2f} | 1:{pick['rr']:.1f} | {pick['shares']} | {pick['sentiment']} |")
    
    report.append(f"\n## Watchlist (Strong Fundamentals, Awaiting Technicals)")
    report.append(", ".join(watchlist) if watchlist else "None")
    
    report.append(f"\n## Avoid/Exit Signals")
    report.append("Review overbought (RSI > 70) and death cross signals above.")
    
    report.append(f"\n---\n*Disclaimer: This is AI-generated analysis for informational purposes only and not financial advice.*")

    output_text = "\n".join(report)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
    else:
        print(output_text)

if __name__ == "__main__":
    main()
