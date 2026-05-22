"""
Dalal Street Live — Market Data Server
"""

from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import feedparser
import requests
import time
import os

app = Flask(__name__)
CORS(app)

SYMBOLS = [
    {'sym': '^NSEI',     'label': 'NIFTY 50',    'id': 'n50'},
    {'sym': '^BSESN',    'label': 'SENSEX',       'id': 'snx'},
    {'sym': '^NSEBANK',  'label': 'BANK NIFTY',   'id': 'bnk'},
    {'sym': '^CNXIT',    'label': 'NIFTY IT',     'id': 'nit'},
    {'sym': '^NSMIDCP',  'label': 'NIFTY MIDCAP', 'id': 'mid'},
    {'sym': 'USDINR=X',  'label': 'INR/USD',      'id': 'inr'},
    {'sym': '^INDIAVIX', 'label': 'INDIA VIX',    'id': 'vix'},
]

RSS_FEEDS = [
    {'url': 'https://economictimes.indiatimes.com/markets/rss.cms',  'source': 'Economic Times'},
    {'url': 'https://www.moneycontrol.com/rss/latestnews.xml',       'source': 'Moneycontrol'},
    {'url': 'https://www.livemint.com/rss/markets',                  'source': 'LiveMint'},
    {'url': 'https://www.business-standard.com/rss/markets-106.rss', 'source': 'Business Standard'},
    {'url': 'https://feeds.feedburner.com/NDTV-Profit-Latest',       'source': 'NDTV Profit'},
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}

_quotes_cache = {}; _quotes_ts = 0
_news_cache   = {}; _news_ts   = 0
QUOTES_TTL = 30; NEWS_TTL = 120

def ist():
    now = time.time()
    return time.strftime('%H:%M:%S', time.gmtime(now + 5.5*3600)) + ' IST'

def fetch_quotes():
    global _quotes_cache, _quotes_ts
    now = time.time()
    if _quotes_cache and (now - _quotes_ts) < QUOTES_TTL:
        return _quotes_cache
    result = []
    try:
        tickers = yf.Tickers(' '.join(s['sym'] for s in SYMBOLS))
        for s in SYMBOLS:
            try:
                fi = tickers.tickers[s['sym']].fast_info
                price = round(float(fi.last_price), 2)
                prev  = round(float(fi.previous_close), 2)
                chg   = round((price-prev)/prev*100, 2) if prev else 0
                result.append({'sym':s['sym'],'label':s['label'],'id':s['id'],'price':price,'prev':prev,'chgPct':chg,'live':True})
            except Exception as e:
                result.append({'sym':s['sym'],'label':s['label'],'id':s['id'],'price':0,'chgPct':0,'live':False,'error':str(e)})
    except Exception as e:
        return {'error':str(e),'data':[],'updated':'—'}
    updated = ist()
    _quotes_cache = {'data':result,'updated':updated,'source':'yfinance'}
    _quotes_ts = now
    nifty = next((r['price'] for r in result if r['id']=='n50'),'?')
    print(f"  [quotes] {updated} | NIFTY: {nifty}")
    return _quotes_cache

def fetch_news():
    global _news_cache, _news_ts
    now = time.time()
    if _news_cache and (now - _news_ts) < NEWS_TTL:
        return _news_cache
    items = []; seen = set()
    for feed in RSS_FEEDS:
        try:
            # Use requests with browser headers + timeout so sites don't block us
            resp = requests.get(feed['url'], headers=HEADERS, timeout=10)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries[:6]:
                title = (entry.get('title') or '').strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                ts = int(now)
                if getattr(entry, 'published_parsed', None):
                    try: ts = int(time.mktime(entry.published_parsed))
                    except: pass
                items.append({'title':title,'publisher':feed['source'],'time':ts,'link':entry.get('link','#')})
        except Exception as e:
            print(f"  [news] {feed['source']} failed: {e}")
    items.sort(key=lambda x: x['time'], reverse=True)
    items = items[:20]
    updated = ist()
    _news_cache = {'news':items,'count':len(items),'updated':updated,'source':'rss'}
    _news_ts = now
    print(f"  [news] {updated} | {len(items)} headlines")
    return _news_cache

@app.route('/api/quotes')
def quotes():
    return jsonify(fetch_quotes())

@app.route('/api/news')
def news():
    return jsonify(fetch_news())

@app.route('/api/status')
def status():
    return jsonify({'status':'ok','time':ist()})

@app.route('/')
def home():
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ('index.html', 'dalal-street-live.html', 'DALAL-~~1.HTM'):
        p = os.path.join(base, name)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify({'status':'running','routes':['/api/quotes','/api/news','/api/status']})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"\n🟢  Dalal Street Live on port {port}\n")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
