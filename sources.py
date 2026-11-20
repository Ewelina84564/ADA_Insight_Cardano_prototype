"""Independent market, on-chain and news sources. Missing data is never silently invented."""
from __future__ import annotations
from datetime import datetime, timezone
import os
import requests
import pandas as pd
import feedparser

HEADERS = {'User-Agent': 'ADAInsight-Educational/1.0 (analytics demo)'}


def fetch_json(url: str, *, params=None, headers=None):
    response = requests.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=20)
    response.raise_for_status()
    return response.json()


def market_data(days: int = 90):
    base = 'https://api.coingecko.com/api/v3/coins/cardano'
    raw = fetch_json(base + '/market_chart', params={'vs_currency': 'usd', 'days': days})
    daily = pd.DataFrame(raw['prices'], columns=['timestamp', 'close'])
    daily['date'] = pd.to_datetime(daily['timestamp'], unit='ms', utc=True).dt.floor('D')
    volumes = pd.DataFrame(raw.get('total_volumes', []), columns=['timestamp', 'volume'])
    volumes['date'] = pd.to_datetime(volumes['timestamp'], unit='ms', utc=True).dt.floor('D')
    # Some API ranges return multiple samples a day.
    daily = daily.groupby('date', as_index=False).agg(close=('close', 'last'))
    volumes = volumes.groupby('date', as_index=False).agg(volume=('volume', 'last'))
    frame = daily.merge(volumes, on='date', how='left')
    frame['date'] = frame['date'].dt.tz_convert(None)
    detail = fetch_json(base, params={'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data':'false', 'developer_data':'false'})
    return frame, detail


def defi_data():
    """TVL in Cardano DeFi protocols via DefiLlama chains API."""
    chains = fetch_json('https://api.llama.fi/v2/chains')
    match = next((x for x in chains if x.get('name','').lower() == 'cardano'), None)
    if match is None: raise ValueError('Cardano не найден в данных DefiLlama')
    return match


def blockfrost_stats():
    """Blockfrost provides Cardano transactions, fees and stake data; requires user API key."""
    key = os.getenv('BLOCKFROST_PROJECT_ID', '').strip()
    if not key:
        return None, 'Для ончейн-метрик укажите BLOCKFROST_PROJECT_ID в переменных окружения.'
    base = 'https://cardano-mainnet.blockfrost.io/api/v0'
    auth = {'project_id': key}
    latest = fetch_json(base + '/blocks/latest', headers=auth)
    epoch = fetch_json(base + '/epochs/latest', headers=auth)
    # Blockfrost latest epoch provides a total transaction count, fees and stake.
    return {'block_height': latest.get('height'), 'block_time': latest.get('time'),
            'epoch': epoch.get('epoch'), 'epoch_tx_count': epoch.get('tx_count'),
            'epoch_fees_lovelace': epoch.get('fees'), 'epoch_active_stake_lovelace': epoch.get('active_stake')}, None


def news(limit: int = 60):
    """Google News RSS: search explicitly scoped to Cardano; feed timestamps may be incomplete."""
    feed_url = 'https://news.google.com/rss/search?q=Cardano%20ADA%20cryptocurrency&hl=en-US&gl=US&ceid=US:en'
    response = requests.get(feed_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    results = []
    for item in feed.entries:
        title = item.get('title', '')
        if not ('cardano' in title.lower() or ' ada ' in f' {title.lower()} '):
            continue
        dt = item.get('published_parsed')
        published = datetime(*dt[:6], tzinfo=timezone.utc).isoformat() if dt else None
        results.append({'title':title, 'published':published, 'url':item.get('link')})
    return results[:limit]

POS = {'surge','gain','grow','growth','bullish','rise','rally','upgrade','launch','adoption','partnership','record','boost','positive','strong','recovery','breakthrough','approval'}
NEG = {'fall','drop','decline','crash','bearish','loss','hack','scam','fraud','risk','down','lawsuit','delay','outage','attack','weak','selloff','warning'}


def sentiment(text: str) -> int:
    """Transparent rule-based EN headline sentiment, not a trained NLP classifier."""
    import re
    words = set(re.findall(r'[a-z]+', text.lower()))
    return (1 if len(words & POS) > len(words & NEG) else -1 if len(words & NEG) > len(words & POS) else 0)
