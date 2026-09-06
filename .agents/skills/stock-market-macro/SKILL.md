---
name: stock-market-macro
description: Analyze macroeconomic conditions and sector rotation to contextualize stock investments. Tracks GDP growth, unemployment, inflation (CPI), Federal Reserve interest rates, and sector ETF relative strength. Classifies market phases (early/mid/late cycle, recession) and identifies favored sectors. Use when the user asks about 'market conditions', 'sector analysis', 'economic indicators', 'sector rotation', 'macro outlook', 'interest rates', 'GDP', 'inflation', 'Fed rates', 'which sectors are hot', 'market cycle', 'recession risk', 'economic data', or any request to understand the broader market environment.
---

# Market Macro & Sector Rotation Skill

## Overview
The `macro_dashboard.py` script queries the FRED API for economic indicators and the Alpha Vantage API for sector ETF prices.

## World Monitor Data Sources
- **Fear & Greed Index** (from get_market_data)
- **COT Positioning** (from get_economic_data)
- **Prediction Markets** (from get_prediction_markets — top geopolitical events affecting markets)
- **Commodity prices** — oil, gold, copper, natural gas (from get_market_data)
- **Chokepoint status summary** (from get_chokepoint_status — disrupted straits)
- **Energy disruptions** (from get_energy_intelligence)

## Economic Indicators Tracked
- **GDP Growth (GDPC1):** Real Gross Domestic Product
- **Unemployment Rate (UNRATE):** Percentage of labor force jobless
- **Inflation (CPIAUCSL):** Consumer Price Index
- **Fed Funds Rate (FEDFUNDS):** Target interest rate
- **Yield Curve (T10Y2Y):** 10yr minus 2yr Treasury spread

## Sector Rotation Model
Tracks 11 SPDR Sector ETFs: XLK, XLF, XLE, XLV, XLI, XLC, XLY, XLP, XLRE, XLU, XLB

## Market Phase Classification
- **Early Cycle:** GDP accelerating, unemployment falling, rates low, yield curve steep. Favored: Financials, Real Estate, Consumer Discretionary.
  - *Geopolitical Overlay:* Stable prediction markets and easing chokepoints reinforce growth sectors.
- **Mid Cycle:** GDP stable/peaking, full employment, rates rising. Favored: Technology, Industrials, Communication Services.
  - *Geopolitical Overlay:* Rising fear/greed or tech supply chain disruptions may temper tech rotation.
- **Late Cycle:** GDP slowing, inflation rising, rates high, yield curve flat/inverted. Favored: Energy, Materials, Health Care.
  - *Geopolitical Overlay:* Late Cycle + chokepoint disruptions + rising conflict = stronger energy/materials signal.
- **Recession:** GDP contracting, unemployment rising, rates being cut. Favored: Consumer Staples, Utilities.
  - *Geopolitical Overlay:* Extreme fear & greed scores and flight-to-safety signals amplify defensive positioning.

## Commodity Correlation
When geopolitical events occur, commodity price action provides confirmation for sector rotation:
- **Oil:** Spikes due to Middle East/Hormuz disruptions reinforce energy sector rotation and act as a headwind for consumer discretionary.
- **Gold:** Spikes on Fear & Greed < 20 or escalating conflicts drive safe-haven rotation.
- **Copper:** Sensitive to global growth shifts and infrastructure spending signaled by prediction markets.

## Usage
```bash
python3 scripts/macro_dashboard.py
```

Environment Variables Required:
- `FRED_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `WORLDMONITOR_API_KEY`

## Integration
- **READ**: World Monitor MCP data via the world-intelligence skill.

Disclaimer: AI-generated analysis for informational purposes only, not financial advice.
