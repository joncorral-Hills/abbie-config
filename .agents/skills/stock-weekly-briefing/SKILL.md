---
name: stock-weekly-briefing
description: "Generate a comprehensive weekly stock investment briefing by orchestrating fundamental, technical, sentiment, and macro analysis skills. Produces scored stock picks with entry zones, stop losses, targets, and risk-reward ratios. Includes portfolio health checks, watchlist items, and exit signals. Use when the user asks for 'weekly stock briefing', 'weekly investment review', 'stock suggestions', 'what should I invest in', 'Allie stock tips', 'weekly picks', 'portfolio review', 'investment suggestions', 'give me stock ideas', 'run the weekly analysis', 'Sunday briefing', or any request for comprehensive weekly investment analysis and recommendations."
---

# Weekly Stock Briefing — Orchestrator Skill

This is the master skill that orchestrates all four analysis skills into one weekly investment briefing.

## Pipeline Steps

0. **Fetch portfolio context**: Query Robinhood MCP for current positions, buying power, and recent trades to tailor analysis to Jon's actual holdings, flag exit signals on current positions, calculate portfolio concentration risk, and size new recommendations against actual buying power.
1. **Run macro scan**: Determine market phase and favored sectors.
1b. **Run geopolitical correlation scan**: Pulls data from the world-intelligence skill's Module E output (JSON artifact from Sunday WI4 cron).
2. **Run fundamental screen**: Filter stock universe by favored sectors and strong fundamentals.
3. **Run technical scan**: Evaluate stocks that pass fundamentals for entry signals.
4. **Run sentiment check**: Confirm technically ready stocks with positive sentiment.
5. **Apply risk management rules**: Calculate position sizing, stop losses, and targets.
6. **Generate scored briefing**: Produce a formatted markdown report.

## Geopolitical Correlation Layer

The weekly briefing now incorporates geopolitical signals to adjust risk and sector allocations:
- Country risk scores for countries with portfolio exposure
- Chokepoint disruption status (Hormuz, Suez, Bab el-Mandeb) and impact on energy/shipping
- Fear & Greed Index composite
- Prediction market probabilities for market-moving geopolitical events
- Energy disruption signals affecting oil/gas sector picks
- Conflict escalation signals affecting defense sector rotation

### Geopolitical Report Template
```
## 🌍 Geopolitical Context
### Market Regime Signal
- Fear & Greed: [score] ([label])
- Prediction Markets: [top 3 market-moving events with probabilities]

### Risk Signals
- Country Risk Movers: [countries with CII delta > 5]
- Chokepoint Status: [any disrupted chokepoints]
- Energy Disruptions: [active disruptions]
- Active Conflicts: [escalation signals]

### Sector Impact
- [How geopolitical signals affect sector rotation recommendations]
```

## Risk Management Rules

| Rule | Description |
|------|-------------|
| **Single stock max** | 5% of portfolio |
| **Single sector max** | 20% of portfolio |
| **Risk per trade** | 1% of equity |
| **Stop loss** | 2 × ATR(14) below entry |
| **Trailing stop** | 3 × ATR from peak (activate at +1.5 ATR) |
| **Min risk-reward** | 1:2.5 |
| **Correlation limit** | Block if pair > 0.70 |
| **Daily drawdown kill** | Halt if down > 2% |

## Instructions

1. Run the `scripts/weekly_pipeline.py` script. Note: Ensure the WI4 cron from the world-intelligence skill has run before starting the weekly pipeline.
2. Provide necessary environment variables: `FMP_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `WORLDMONITOR_API_KEY`.
3. Save the resulting output as a markdown artifact for the user to review.
4. The output follows the template defined in `references/report_template.md`.

## Integration

- **READ**: World-intelligence skill's Module E correlation output (JSON artifact).
- **READ**: Robinhood MCP — `get_account`, `get_positions`, `get_watchlist` for portfolio context.
- **WRITE**: `resources/portfolio_snapshot.json` — cached positions for financial-planner Net Worth module.

*Disclaimer: All analysis is for informational purposes only and does not constitute financial advice.*
