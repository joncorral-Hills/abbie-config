#!/usr/bin/env python3
import sys
import argparse
import os
import json
import urllib.request
import urllib.error
import time
from datetime import datetime
import math

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period # start with SMA
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    for i in range(1, period + 1):
        change = prices[i] - prices[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # Wilder's Smoothing
    for i in range(period + 1, len(prices)):
        change = prices[i] - prices[i-1]
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal_period=9):
    if len(prices) < slow + signal_period:
        return None, None, None
    
    multiplier_fast = 2 / (fast + 1)
    multiplier_slow = 2 / (slow + 1)
    
    fast_ema = sum(prices[:fast]) / fast
    slow_ema = sum(prices[:slow]) / slow
    
    macd_series = []
    
    for i in range(slow, len(prices)):
        if i == slow:
            fast_ema = sum(prices[:fast]) / fast
            for j in range(fast, slow):
                fast_ema = (prices[j] - fast_ema) * multiplier_fast + fast_ema
                
        fast_ema = (prices[i] - fast_ema) * multiplier_fast + fast_ema
        slow_ema = (prices[i] - slow_ema) * multiplier_slow + slow_ema
        macd_series.append(fast_ema - slow_ema)
        
    if len(macd_series) < signal_period:
        return None, None, None
        
    signal_line = calculate_ema(macd_series, signal_period)
    macd_val = macd_series[-1]
    hist = macd_val - signal_line
    
    return macd_val, signal_line, hist

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None, None, None
    
    recent_prices = prices[-period:]
    sma = sum(recent_prices) / period
    
    variance = sum((x - sma) ** 2 for x in recent_prices) / period
    std = math.sqrt(variance)
    
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    
    return upper, sma, lower

def fetch_data(ticker, api_key):
    # Use TIME_SERIES_DAILY (free tier) with compact output (100 trading days)
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={api_key}"
    req = urllib.request.Request(url, headers={'User-Agent': 'AllieStockAdvisor/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            if "Error Message" in data:
                return None, data["Error Message"]
            if "Note" in data or "Information" in data:
                msg = data.get("Note", data.get("Information", "Rate limit or premium"))
                return None, msg
            
            ts = data.get("Time Series (Daily)", {})
            if not ts:
                return None, "No data"
                
            sorted_dates = sorted(ts.keys())
            closes = []
            volumes = []
            highs = []
            lows = []
            
            for date in sorted_dates:
                closes.append(float(ts[date]["4. close"]))
                volumes.append(float(ts[date]["5. volume"]))
                highs.append(float(ts[date]["2. high"]))
                lows.append(float(ts[date]["3. low"]))
                
            return (closes, volumes, highs, lows, sorted_dates), None
    except Exception as e:
        return None, str(e)

def analyze_ticker(ticker, data_tuple):
    closes, volumes, highs, lows, dates = data_tuple
    
    if len(closes) < 30:
        return {"error": f"Not enough data ({len(closes)} days, need 30+)"}
        
    current_price = closes[-1]
    
    sma_50 = calculate_sma(closes, 50)
    sma_200 = calculate_sma(closes, 200)
    ema_50 = calculate_ema(closes, 50)
    ema_200 = calculate_ema(closes, 200)
    rsi_14 = calculate_rsi(closes, 14)
    macd, signal, hist = calculate_macd(closes)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(closes)
    
    vol_20d_avg = sum(volumes[-20:]) / 20
    accumulation_days = 0
    for i in range(1, 11):
        if closes[-i] > closes[-(i+1)] and volumes[-i] > 1.5 * vol_20d_avg:
            accumulation_days += 1
            
    pivots_low = []
    pivots_high = []
    window = 20
    for i in range(window, len(closes) - window):
        is_low = True
        is_high = True
        for j in range(1, window + 1):
            if lows[i] > lows[i-j] or lows[i] > lows[i+j]:
                is_low = False
            if highs[i] < highs[i-j] or highs[i] < highs[i+j]:
                is_high = False
        if is_low:
            pivots_low.append(lows[i])
        if is_high:
            pivots_high.append(highs[i])
            
    nearest_support = max([p for p in pivots_low if p < current_price], default=None)
    nearest_resistance = min([p for p in pivots_high if p > current_price], default=None)
    
    signals = {}
    score = 50
    
    if sma_200 and current_price > sma_200:
        signals["trend"] = "bullish"
        score += 10
    else:
        signals["trend"] = "bearish"
        score -= 10
        
    if sma_50:
        sma_50_prev = calculate_sma(closes[:-5], 50)
        if sma_200 and sma_50_prev:
            sma_200_prev = calculate_sma(closes[:-5], 200)
            if sma_200_prev and sma_50_prev < sma_200_prev and sma_50 > sma_200:
                signals["golden_cross"] = True
                score += 20
            elif sma_200_prev and sma_50_prev > sma_200_prev and sma_50 < sma_200:
                signals["death_cross"] = True
                score -= 20
        
    if rsi_14:
        if rsi_14 > 70:
            signals["rsi_status"] = "overbought"
            score -= 10
        elif rsi_14 < 30:
            signals["rsi_status"] = "oversold"
            score += 10
        elif 35 <= rsi_14 <= 45 and sma_200 and current_price > sma_200:
            signals["rsi_status"] = "pullback_entry"
            score += 15
        else:
            signals["rsi_status"] = "neutral"
        
    if macd and signal:
        prev_macd, prev_signal, _ = calculate_macd(closes[:-1])
        if prev_macd and prev_signal and prev_macd < prev_signal and macd > signal and macd < 0:
            signals["macd_cross"] = "bullish"
            score += 15
        elif prev_macd and prev_signal and prev_macd > prev_signal and macd < signal and macd > 0:
            signals["macd_cross"] = "bearish"
            score -= 15
            
    if bb_mid:
        bb_width = (bb_upper - bb_lower) / bb_mid
        if bb_width < 0.05: 
            signals["bollinger_squeeze"] = True
        
    if accumulation_days >= 3:
        signals["accumulation"] = True
        score += 15
        
    score = max(0, min(100, score))
    
    return {
        "ticker": ticker,
        "score": score,
        "price": round(current_price, 2),
        "signals": signals,
        "indicators": {
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "sma_200": round(sma_200, 2) if sma_200 else None,
            "rsi_14": round(rsi_14, 2) if rsi_14 else None,
            "macd": round(macd, 2) if macd else None,
            "macd_signal": round(signal, 2) if signal else None
        },
        "support": round(nearest_support, 2) if nearest_support else None,
        "resistance": round(nearest_resistance, 2) if nearest_resistance else None
    }

def main():
    parser = argparse.ArgumentParser(description="Scan stocks for technical signals.")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols to analyze")
    args = parser.parse_args()
    
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print(json.dumps({"error": "ALPHA_VANTAGE_API_KEY environment variable not set"}))
        sys.exit(1)
        
    results = []
    
    for i, ticker in enumerate(args.tickers):
        ticker = ticker.upper()
        if i > 0:
            time.sleep(12) # Alpha vantage rate limit
            
        data, err = fetch_data(ticker, api_key)
        if err:
            results.append({"ticker": ticker, "error": err})
            continue
            
        analysis = analyze_ticker(ticker, data)
        results.append(analysis)
        
    output = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "disclaimer": "This is AI-generated analysis for informational purposes only and not financial advice."
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
