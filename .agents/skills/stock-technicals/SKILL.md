---
name: stock-technicals
description: Analyze stocks using technical indicators for optimal entry and exit timing — moving averages (SMA/EMA), RSI, MACD, Bollinger Bands, volume analysis, and support/resistance levels. Identifies golden crosses, death crosses, oversold conditions, volatility squeezes, and accumulation patterns. Use when the user asks for 'technical analysis', 'chart analysis', 'entry point', 'buy signal', 'sell signal', 'RSI', 'MACD', 'moving averages', 'overbought', 'oversold', 'golden cross', 'death cross', 'support resistance', 'volume analysis', 'when to buy', or any request to time a stock entry or exit.
---

# Stock Technical Analysis Skill

This skill performs technical analysis on given stock tickers to help determine optimal entry and exit points based on price action, momentum, and volume indicators.

## Included Indicators and Signals

| Indicator | Signal Criteria | Description |
|---|---|---|
| **Trend** | Price > 200-SMA, 50-EMA > 200-EMA | Confirms the primary trend direction. |
| **Golden/Death Cross** | 50-SMA crosses above/below 200-SMA | Long-term momentum shift signal. |
| **RSI (14-day)** | Avoid > 70 (Overbought), Flag < 30 (Oversold), Pullback Entry 35-45 | Measures momentum. Bullish divergence (price new low + RSI higher low) is also tracked. |
| **MACD (12,26,9)** | MACD crosses above Signal from below zero | Momentum shift confirmation. |
| **Bollinger Squeeze** | Bandwidth in lowest 10th percentile of 100 days. Breakout on close > upper band. | Identifies low volatility periods preceding strong directional moves. |
| **Volume Accumulation** | Price up on > 1.5x 20-day avg vol, 3+ days in 10-day window | Detects institutional buying pressure. |
| **Support/Resistance** | 20-period pivot window swing detection | Identifies key price levels for risk management. |

## Execution Instructions

Run the included Python script to scan tickers:

```bash
python3 scripts/technical_scan.py AAPL MSFT TSLA
```

Prerequisites:
- An Alpha Vantage API key must be set in the `ALPHA_VANTAGE_API_KEY` environment variable.

Interpreting Results (Confluence):
- Do not rely on a single indicator. Look for signal confluence — when multiple indicators align.

Disclaimer:
IMPORTANT: This is an AI-generated analysis for informational purposes only and does NOT constitute financial advice.
