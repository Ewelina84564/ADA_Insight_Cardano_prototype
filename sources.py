"""Public API adapters for Cardano. Network failures always raise visible exceptions."""
from __future__ import annotations
import os
import re
import math
from datetime import datetime, timezone
import pandas as pd
import requests
import feedparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {'User-Agent': 'ADAInsight-Education/2.0 (Streamlit research dashboard)', 'Accept': 'application/json'}


def session():
    s = requests.Session()
    retries = Retry(total=2, connect=2, read=1, backoff_factor=.6,
                    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=['GET'])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    return s


def fetch_json(url, *, params=None, headers=None):
    r = session().get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=(5, 14))
    r.raise_for_status()
    return r.json()


def market_data(days=90):
    base = 'https://api.coingecko.com/api/v3/coins/cardano'
    raw = fetch_json(base + '/market_chart', params={'vs_currency':'usd','days':int(days)})
    if not isinstance(raw, dict) or not raw.get('prices'):
        raise ValueError('CoinGecko не вернул историю цены ADA')
    prices = pd.DataFrame(raw['prices'], columns=['timestamp','close'])
    prices['date'] = pd.to_datetime(prices['timestamp'],unit='ms',utc=True).dt.floor('D')
    prices = prices.groupby('date',as_index=False).agg(close=('close','last'))
    volumes = raw.get('total_volumes') or []
    if volumes:
        vol = pd.DataFrame(volumes,columns=['timestamp','volume'])
        vol['date'] = pd.to_datetime(vol['timestamp'],unit='ms',utc=True).dt.floor('D')
        vol = vol.groupby('date',as_index=False).agg(volume=('volume','last'))
        prices = prices.merge(vol,on='date',how='left')
    else:
        prices['volume'] = float('nan')
    prices['date'] = prices['date'].dt.tz_localize(None)
    # Detail request may fail separately: return valid history rather than discarding it.
    detail = None
    detail_error = None
    try:
        detail = fetch_json(base,params={'localization':'false','tickers':'false','market_data':'true','community_data':'false','developer_data':'false'})
    except Exception as exc:
        detail_error = f'CoinGecko (подробные данные): {type(exc).__name__}: {exc}'
    return prices, detail, detail_error


def defi_data():
    records = fetch_json('https://api.llama.fi/v2/chains')
    match = next((v for v in records if str(v.get('name','')).lower() == 'cardano'), None)
    if match is None:
        raise ValueError('Cardano отсутствует в ответе DefiLlama')
    return match


def blockfrost_stats(key=None, history_count=8):
    """Fetch last finished Cardano epochs. Current epoch may be incomplete; exclude it."""
    key = (key or os.getenv('BLOCKFROST_PROJECT_ID', '')).strip()
    if not key:
        return None, 'Не указан BLOCKFROST_PROJECT_ID (Secrets); ончейн-метрики недоступны.'
    base='https://cardano-mainnet.blockfrost.io/api/v0'
    headers={'project_id':key}
    latest = fetch_json(base+'/epochs/latest',headers=headers)
    newest = int(latest['epoch'])
    epochs=[]
    for epoch_num in range(max(0,newest-int(history_count)),newest):
        ep=fetch_json(base+f'/epochs/{epoch_num}',headers=headers)
        epochs.append({'epoch':ep.get('epoch'),'tx_count':ep.get('tx_count'),
                       'fees_ada':number(ep.get('fees'),factor=1e6),
                       'active_stake_ada':number(ep.get('active_stake'),factor=1e6),
                       'start_time':ep.get('start_time')})
    return epochs, None


def number(value, factor=1):
    try:
        result = float(value)/factor if value is not None else None
        return result if result is None or math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError): return None


def news(limit=60):
    url='https://news.google.com/rss/search?q=Cardano%20ADA%20cryptocurrency&hl=en-US&gl=US&ceid=US:en'
    r=session().get(url,headers={'User-Agent':HEADERS['User-Agent']},timeout=(5,14))
    r.raise_for_status()
    feed=feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError('Некорректный RSS Google News')
    seen=set(); articles=[]
    for entry in feed.entries:
        title=str(entry.get('title','')).strip()
        if not re.search(r'\b(cardano|ada)\b',title,re.I): continue
        normalized=re.sub(r'\W+',' ',title.lower()).strip()
        if normalized in seen: continue
        seen.add(normalized)
        pt=entry.get('published_parsed')
        dt=datetime(*pt[:6],tzinfo=timezone.utc).isoformat() if pt else None
        articles.append({'title':title,'published':dt,'url':entry.get('link','')})
    return articles[:limit]

POS={'surge','gain','grow','growth','bullish','rise','rally','upgrade','launch','adoption','partnership','record','boost','positive','strong','recovery','breakthrough','approval'}
NEG={'fall','drop','decline','crash','bearish','loss','hack','scam','fraud','risk','down','lawsuit','delay','outage','attack','weak','selloff','warning'}
def sentiment(text):
    words=set(re.findall(r'[a-z]+',str(text).lower()))
    p=len(words & POS); n=len(words & NEG)
    return 1 if p>n else -1 if n>p else 0
