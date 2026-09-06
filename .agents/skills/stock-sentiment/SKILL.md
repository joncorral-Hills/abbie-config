---
name: stock-sentiment
description: "Analyze market sentiment for stocks using news sentiment scores, social media buzz, analyst consensus ratings, insider trading signals, and institutional ownership changes. Detects bullish/bearish sentiment shifts, insider cluster buying, and institutional accumulation. Use when the user asks about 'market sentiment', 'news analysis', 'insider buying', 'insider selling', 'analyst ratings', 'social buzz', 'what\'s trending', 'institutional ownership', 'is sentiment positive', 'what are analysts saying', 'insider transactions', or any request to gauge market mood around a stock."
---

# Market Sentiment Analyzer

Analyzes sentiment using multiple data streams to detect shifts in market mood.

## Signal Thresholds

| Signal | Bullish | Bearish |
|--------|---------|----------|
| **News Polarity** | > 0.25 (positive articles dominate) | < -0.25 |
| **Analyst Consensus** | Rating > 4.0 AND target > 15% upside | Rating < 2.5 OR target < current price |
| **Insider Trades** | 3+ distinct insiders buying in 30 days (exclude 10b5-1) | Significant cluster selling |
| **Institutional Flows** | Net inflows > 2% of float in trailing quarter | Net outflows > 2% |

## Instructions

1. Identify the ticker symbols the user wants to analyze.
2. Run the sentiment scan script: `python3 scripts/sentiment_scan.py <TICKER1> [TICKER2] ...`
3. Ensure the `FINNHUB_API_KEY` environment variable is set.
4. Analyze the JSON output and evaluate the signals against the thresholds above.
5. Cross-reference sentiment with technical or fundamental data if applicable.
6. Always include the mandatory financial disclaimer in your response.

**IMPORTANT**: All investment-related output must include a disclaimer that this is AI-generated analysis for informational purposes only and not financial advice.
