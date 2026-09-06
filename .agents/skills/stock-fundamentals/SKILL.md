---
name: stock-fundamentals
description: Screen and analyze stocks using fundamental financial metrics — P/E ratio, PEG, EPS growth, revenue growth, debt-to-equity, free cash flow yield, and dividend sustainability. Evaluates company financial health using SEC EDGAR and Financial Modeling Prep data. Use when the user asks to 'analyze fundamentals', 'stock health check', 'screen stocks', 'find undervalued stocks', 'earnings analysis', 'financial metrics', 'company financials', 'is this stock a good buy fundamentally', or any request to evaluate a company's financial health and valuation.
---

# Stock Fundamentals Screener

This skill evaluates a company's financial health and valuation by pulling data from the SEC EDGAR API and Financial Modeling Prep, applying a rigorous set of fundamental screening gates.

## Screening Gates Table

| Metric | Ideal/Pass Threshold | Reject Threshold | Notes |
|:---|:---|:---|:---|
| **PEG Ratio** | < 1.0 | > 2.0 | Best measure of value relative to growth. |
| **P/E vs 5yr Median** | Within ±15% | N/A | Assesses historical valuation consistency. |
| **YoY EPS Growth** | > 10% | < 0% | Shows profitability growth. |
| **YoY Revenue Growth** | > 8% | < 0% | Top-line expansion is crucial. |
| **Debt-to-Equity** | < 1.5 | > 2.0 | Sector adjustments: Tech < 1.0; Utilities/Financials < 2.5. |
| **FCF Yield** | > 5% | < 0% | Free cash flow yield indicates cash generation ability. |
| **Dividend Payout** | 30% - 60% | > 80% | Determines dividend sustainability. |

**Earnings Signals:**
*   **Earnings Surprise:** (Actual - Estimate)/Estimate > 5% is a strong positive signal.
*   **Forward Guidance:** Analyst revisions upward > 2% in the week post-earnings.

## Instructions for the Agent

1. Check that the required API keys are available in the environment variables:
   *   `FMP_API_KEY`: Financial Modeling Prep API Key.
   *   `FINNHUB_API_KEY`: Finnhub API Key (if applicable for other data).

2. Run the screening script from the `scripts` directory using Python.

```bash
# To screen specific tickers:
python3 scripts/fundamental_screen.py AAPL MSFT GOOGL

# To screen the S&P 500 (requires network access to fetch list):
python3 scripts/fundamental_screen.py --universe sp500
```

3. Interpret the Output: The script outputs JSON containing a score (0-100) and the specific gates passed/failed for each ticker. A score > 80 is excellent, 60-80 is acceptable, and < 60 generally warrants rejection based on fundamentals alone.

4. Reference Metrics: For deep dives, edge cases (REITs, Financials, negative earnings), and exact formulas, refer to `references/metric_definitions.md`.

5. Disclaimer: ALWAYS include a disclaimer in your response that the analysis is AI-generated for informational purposes only and is not financial advice.
