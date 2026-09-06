#!/usr/bin/env python3
"""
Scan market sentiment using news, analyst ratings, and insider transactions.
"""
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import os
from datetime import datetime, timedelta
import re

# Basic positive/negative word lists for NLP sentiment scoring
POSITIVE_WORDS = {
    'upgrade', 'upgrades', 'bullish', 'growth', 'surge', 'surges', 'beat', 'beats',
    'outperform', 'buy', 'strong', 'positive', 'profit', 'profitable', 'record',
    'breakout', 'dividend', 'increase', 'increases', 'raised', 'raises', 'soar', 'soars',
    'gains', 'gain', 'opportunity', 'promising', 'success'
}

NEGATIVE_WORDS = {
    'downgrade', 'downgrades', 'bearish', 'decline', 'declines', 'miss', 'misses',
    'underperform', 'sell', 'weak', 'negative', 'loss', 'losses', 'slump',
    'breakdown', 'cut', 'cuts', 'decreased', 'decreases', 'plunge', 'plunges',
    'drop', 'drops', 'risk', 'warning', 'lawsuit', 'investigation'
}

def get_finnhub_data(endpoint, params=None):
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return None
    
    base_url = "https://finnhub.io/api/v1"
    url = f"{base_url}{endpoint}?token={api_key}"
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}&{query_string}"
        
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        return None

def calculate_news_sentiment(news_items):
    if not news_items:
        return {"polarity": 0, "bullish_count": 0, "bearish_count": 0, "article_count": 0}
        
    bullish_count = 0
    bearish_count = 0
    total_score = 0
    
    for item in news_items:
        text = f"{item.get('headline', '')} {item.get('summary', '')}".lower()
        words = re.findall(r'\b\w+\b', text)
        
        pos_hits = sum(1 for w in words if w in POSITIVE_WORDS)
        neg_hits = sum(1 for w in words if w in NEGATIVE_WORDS)
        
        score = pos_hits - neg_hits
        total_score += score
        if score > 0:
            bullish_count += 1
        elif score < 0:
            bearish_count += 1
            
    article_count = len(news_items)
    polarity = total_score / (article_count * 2) if article_count > 0 else 0
    polarity = max(-1.0, min(1.0, polarity)) # clamp between -1 and 1
    
    return {
        "polarity": round(polarity, 2),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "article_count": article_count
    }

def analyze_ticker(ticker):
    result = {
        "ticker": ticker.upper(),
        "sentiment_score": 50, # Neutral baseline
        "news": {},
        "analysts": {},
        "insiders": {},
        "social": {"status": "data unavailable"} # Placeholder for social buzz
    }
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    # 1. News Sentiment (7-day rolling)
    news_start = end_date - timedelta(days=7)
    news_data = get_finnhub_data("/company-news", {"symbol": ticker, "from": news_start.strftime("%Y-%m-%d"), "to": end_str})
    if news_data is not None:
        result["news"] = calculate_news_sentiment(news_data)
    else:
        result["news"] = {"status": "error or missing api key"}
        
    # 2. Analyst Recommendation Trends
    analyst_data = get_finnhub_data("/stock/recommendation", {"symbol": ticker})
    if analyst_data and len(analyst_data) > 0:
        latest = analyst_data[0]
        total_recs = latest.get('strongBuy', 0) + latest.get('buy', 0) + latest.get('hold', 0) + latest.get('sell', 0) + latest.get('strongSell', 0)
        
        if total_recs > 0:
            score = (
                latest.get('strongBuy', 0) * 5 +
                latest.get('buy', 0) * 4 +
                latest.get('hold', 0) * 3 +
                latest.get('sell', 0) * 2 +
                latest.get('strongSell', 0) * 1
            ) / total_recs
        else:
            score = 3.0
            
        result["analysts"] = {
            "consensus_rating": round(score, 2),
            "total_ratings": total_recs,
            "strongBuy": latest.get('strongBuy', 0),
            "buy": latest.get('buy', 0),
            "hold": latest.get('hold', 0),
            "sell": latest.get('sell', 0),
            "strongSell": latest.get('strongSell', 0)
        }
    else:
        result["analysts"] = {"status": "unavailable"}

    # 3. Insider Transactions
    insider_data = get_finnhub_data("/stock/insider-transactions", {"symbol": ticker, "from": start_str, "to": end_str})
    if insider_data and 'data' in insider_data:
        txs = insider_data['data']
        buyers = set()
        sellers = set()
        for tx in txs:
            if tx.get('change', 0) > 0:
                buyers.add(tx.get('name'))
            elif tx.get('change', 0) < 0:
                sellers.add(tx.get('name'))
                
        result["insiders"] = {
            "distinct_buyers_30d": len(buyers),
            "distinct_sellers_30d": len(sellers),
            "cluster_buying": len(buyers) >= 3
        }
    else:
        result["insiders"] = {"status": "unavailable (SEC fallback not implemented in basic script)"}
        
    # Calculate overall score (0-100)
    score = 50
    
    # News effect (+/- 20)
    if result["news"].get("polarity") is not None:
        score += result["news"]["polarity"] * 20
        
    # Analyst effect (+/- 15)
    if result["analysts"].get("consensus_rating") is not None:
        a_score = result["analysts"]["consensus_rating"]
        score += (a_score - 3.0) * 7.5
        
    # Insider effect (+/- 15)
    if result["insiders"].get("cluster_buying"):
        score += 15
    elif result["insiders"].get("distinct_sellers_30d", 0) > 3:
        score -= 10
        
    result["sentiment_score"] = max(0, min(100, int(score)))
    
    return result

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No tickers provided. Usage: script.py <TICKER>"}))
        sys.exit(1)
        
    tickers = sys.argv[1:]
    results = []
    
    for ticker in tickers:
        results.append(analyze_ticker(ticker))
        
    output = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "disclaimer": "This is AI-generated analysis for informational purposes only and not financial advice."
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
