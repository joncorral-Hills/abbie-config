# Risk Management Rules

## Position Sizing Formula
`Shares = (Account Size × Risk %) / (Entry Price - Stop Loss Price)`

**Example**: Portfolio $10,000, Risk 1% ($100), Entry $150, Stop $140, Risk/Share $10 → Buy 10 shares.

## Stop Loss Calculation
- **Initial Stop Loss**: 2 × ATR(14) below entry price
- Allows normal market noise while protecting against structural breakdowns

## Trailing Stop
- **Activation**: Once position is +1.5 ATR in profit
- **Management**: Trail at 3 × ATR from peak price

## Risk-Reward Ratio
- **Minimum Acceptable R:R**: 1:2.5
- Target must be at least 2.5× the stop distance

## Portfolio Concentration Limits
- **Single Stock Max**: 5% of total portfolio equity
- **Single Sector Max**: 20% of total portfolio equity

## Correlation-Based Blocking
- Block new trades if pair correlation with existing holding > 0.70

## Daily Drawdown Kill Switch
- Halt all new trading if portfolio drops > 2% in a single day

*Disclaimer: For informational purposes only, not financial advice.*
