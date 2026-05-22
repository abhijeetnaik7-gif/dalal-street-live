"""
Dalal Street Live — Market Data Server
=======================================
Serves live NSE/BSE index data and real Indian market news via RSS feeds.

Local usage:
    pip install flask flask-cors yfinance feedparser gunicorn
    python app.py

Render/Cloud deployment:
    Render will run:  gunicorn app:app
    Set environment variable PORT if needed (Render sets it automatically).
"""

from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import feedparser
import time
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)  # Allow all origins — needed for browser fetch from any domain

# ── Index symbols ──────────────────────────────────────────────────────────────
SYMBOLS = [
    {'sym': '^NSEI',     'label': 'NIFTY 50',    'id': 'n50'},
    {'sym': '^BSESN',    'label': 'SENSEX',       'id': 'snx'},
    {'sym': '^NSEBANK',  'label': 'BANK NIFTY',   'id': 'bnk'},
    {'sym': '^CNXIT',    'label': 'NIFTY IT',     'id': 'nit'},
    {'sym': '^NSMIDCP',  'label': 'NIFTY MIDCAP', 'id': 'mid'},
    {'sym': 'USDINR=X',  'label': 'INR/USD',      'id': 'inr'},
    {'sym': '^INDIAVIX', 'label': 'INDIA VIX',    'id': 'vix'},
]

# ── RSS news sources (real Indian financial media) ─────────────────────────────
RSS_FEEDS = [
    {'url': 'https://economictimes.indiatimes.com/markets/rss.cms',       'source': 'Economic Times'},
    {'url': 'https://www.moneycontrol.com/rss/latestnews.xml',            'source': 'Moneycontrol'},
    {'url': 'https://www.livemint.com/rss/markets',                       'source': 'LiveMint'},
    {'url': 'https://www.business-standard.com/rss/markets-106.rss',      'source': 'Business Standard'},
    {'url': 'https://feeds.feedburner.com/NDTV-Profit-Latest',            'source': 'NDTV Profit'},
]

# ── In-memory cache ────────────────────────────────────────────────────────────
_quotes_cache    = {}
_quotes_cache_ts = 0
_news_cache      = {}
_news_cache_ts   = 0
QUOTES_TTL = 30   # seconds
NEWS_TTL   = 120  # seconds — RSS feeds don't need to be hit every 30s


# ── Helpers ────────────────────────────────────────────────────────────────────

def ist_time_str():
    """Return current time as HH:MM:SS IST string."""
    now = time.time()
    ist_offset = 5.5 * 3600
    return time.strftime('%H:%M:%S', time.gmtime(now + ist_offset)) + ' IST'


def fetch_quotes():
    global _quotes_cache, _quotes_cache_ts
    now = time.time()
    if _quotes_cache and (now - _quotes_cache_ts) < QUOTES_TTL:
        return _quotes_cache

    result = []
    syms = [s['sym'] for s in SYMBOLS]

    try:
        tickers = yf.Tickers(' '.join(syms))
        for s in SYMBOLS:
            try:
                t  = tickers.tickers[s['sym']]
                fi = t.fast_info
                price   = round(float(fi.last_price), 2)
                prev    = round(float(fi.previous_close), 2)
                chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
                result.append({
                    'sym': s['sym'], 'label': s['label'], 'id': s['id'],
                    'price': price, 'prev': prev, 'chgPct': chg_pct, 'live': True,
                })
            except Exception as e:
                result.append({
                    'sym': s['sym'], 'label': s['label'], 'id': s['id'],
                    'price': 0, 'chgPct': 0, 'live': False, 'error': str(e),
                })
    except Exception as e:
        return {'error': str(e), 'data': [], 'updated': '—'}

    updated = ist_time_str()
    _quotes_cache    = {'data': result, 'updated': updated, 'source': 'yfinance'}
    _quotes_cache_ts = now
    nifty = next((r['price'] for r in result if r['id'] == 'n50'), '?')
    print(f"  [quotes] refreshed at {updated}  |  NIFTY: {nifty}")
    return _quotes_cache


def fetch_news():
    global _news_cache, _news_cache_ts
    now = time.time()
    if _news_cache and (now - _news_cache_ts) < NEWS_TTL:
        return _news_cache

    items = []
    seen_titles = set()

    for feed_cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_cfg['url'])
            for entry in feed.entries[:6]:  # up to 6 items per source
                title = (entry.get('title') or '').strip()
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                # Parse published time
                ts = int(now)
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        ts = int(time.mktime(entry.published_parsed))
                    except Exception:
                        pass

                link = entry.get('link') or '#'
                items.append({
                    'title':     title,
                    'publisher': feed_cfg['source'],
                    'time':      ts,
                    'link':      link,
                })
        except Exception as e:
            print(f"  [news] RSS error ({feed_cfg['source']}): {e}")

    # Sort newest first
    items.sort(key=lambda x: x['time'], reverse=True)
    items = items[:20]  # cap at 20 headlines

    updated = ist_time_str()
    _news_cache    = {'news': items, 'count': len(items), 'updated': updated, 'source': 'rss'}
    _news_cache_ts = now
    print(f"  [news] refreshed at {updated}  |  {len(items)} headlines from {len(RSS_FEEDS)} sources")
    return _news_cache


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/api/quotes')
def quotes():
    return jsonify(fetch_quotes())


@app.route('/api/news')
def news():
    return jsonify(fetch_news())


@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'server': 'Dalal Street Live',
        'time':   ist_time_str(),
    })


@app.route('/')
def home():
    """Serve the main HTML page if it exists alongside this file."""
    # Try common filenames — handles Windows short-name truncation issues
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ('index.html', 'dalal-street-live.html', 'DALAL-~~1.HTM'):
        html_path = os.path.join(base, name)
        if os.path.exists(html_path):
            break
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    return jsonify({'message': 'Dalal Street Live API is running', 'routes': ['/api/quotes', '/api/news', '/api/status']})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"\n🟢  Dalal Street Live server starting on port {port}")
    print(f"    /api/quotes  — live index prices (yfinance)")
    print(f"    /api/news    — Indian market RSS headlines")
    print(f"    /api/status  — health check\n")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
