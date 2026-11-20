"""ADA Insight | educational real-data analytics dashboard."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analytics import indicators, technical_score, integral_score, explain, change_pct
from sources import market_data, defi_data, blockfrost_stats, news, sentiment

DB = Path(__file__).with_name('ada_insight.sqlite3')

@st.cache_data(ttl=900, show_spinner=False)
def cached_market(days): return market_data(days)

@st.cache_data(ttl=1800, show_spinner=False)
def cached_defi(): return defi_data()

@st.cache_data(ttl=1800, show_spinner=False)
def cached_onchain(): return blockfrost_stats()

@st.cache_data(ttl=1800, show_spinner=False)
def cached_news(): return news()


def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, days INTEGER NOT NULL, data TEXT NOT NULL)')
        conn.commit()


def save_run(days, payload):
    with sqlite3.connect(DB) as conn:
        conn.execute('INSERT INTO runs(run_at,days,data) VALUES(?,?,?)', (datetime.now(timezone.utc).isoformat(), days, json.dumps(payload, ensure_ascii=False)))
        conn.commit()


def history():
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query('SELECT * FROM runs ORDER BY id DESC LIMIT 100', conn)


def fmt_money(val, decimals=4):
    return f'${val:,.{decimals}f}' if val is not None else 'Нет данных'

st.set_page_config(page_title='ADA Insight | Cardano', page_icon='🔷', layout='wide')
st.markdown('''<style>
.block-container {padding-top: 1.4rem; max-width: 1450px;}
[data-testid="stMetric"] {border:1px solid #33415c; border-radius:14px; padding:13px;}
h1,h2,h3 {letter-spacing:-.02em;}
</style>''', unsafe_allow_html=True)
init_db()
st.title('🔷 ADA Insight')
st.caption('Cardano (ADA/USD) · Интеллектуальная аналитическая система · Учебный проект')

with st.sidebar:
    st.header('Настройки анализа')
    st.info('Актив: Cardano (ADA). Источники: CoinGecko, DefiLlama, Blockfrost, Google News RSS.')
    days = st.selectbox('Период ценового анализа', [30, 90, 180, 365], index=1, format_func=lambda x: f'{x} дней')
    st.caption('Бесплатные API могут ограничивать историю и частоту обращений.')
    if st.button('🔄 Обновить и пересчитать', type='primary', use_container_width=True):
        cached_market.clear(); cached_defi.clear(); cached_onchain.clear(); cached_news.clear()
        st.rerun()

issues = []
price = detail = defi = onchain = articles = None
with st.spinner('Получаем доступные данные из независимых источников…'):
    try: price, detail = cached_market(days)
    except Exception as exc: issues.append(f'CoinGecko: {exc}')
    try: defi = cached_defi()
    except Exception as exc: issues.append(f'DefiLlama: {exc}')
    try:
        onchain, warning = cached_onchain()
        if warning: issues.append(warning)
    except Exception as exc: issues.append(f'Blockfrost: {exc}')
    try: articles = cached_news()
    except Exception as exc: issues.append(f'Google News: {exc}')

frame = indicators(price) if price is not None and len(price) > 0 else None
ta, ta_signals = technical_score(frame) if frame is not None else (None, ['Нет рыночных данных.'])

# Explicit scoring rubric. No score is invented if required input is absent.
fa = None
fa_factors = []
if detail is not None and defi is not None:
    market = detail.get('market_data') or {}
    cap = (market.get('market_cap') or {}).get('usd')
    fdv = (market.get('fully_diluted_valuation') or {}).get('usd')
    circ = market.get('circulating_supply')
    maxs = market.get('max_supply')
    tvl = defi.get('tvl')
    factors = []
    if cap and fdv:
        factors.append(25 if cap/fdv >= .75 else -25)
        fa_factors.append(f'Market Cap / FDV = {cap/fdv:.2f}; отражает потенциальное размытие.')
    if circ and maxs:
        factors.append(25 if circ/maxs >= .75 else -25)
        fa_factors.append(f'Циркулирующее предложение / максимум = {circ/maxs:.1%}.')
    if cap and tvl is not None:
        factors.append(25 if tvl/cap >= .05 else -25)
        fa_factors.append(f'TVL экосистемы / капитализация = {tvl/cap:.2%}; эвристический порог 5%.')
    if len(factors) == 3: fa = sum(factors) / len(factors) * 4
    else: fa_factors.append('Для количественной оценки недостаточно обязательных метрик.')

on = None
on_factors = []
if onchain:
    # Single snapshot is not evidence of growth or decline: require historical comparisons.
    on_factors.append('Blockfrost предоставляет снимок эпохи; для оценки тренда нужны минимум две сопоставимые эпохи.')

sa = None
news_df = None
if articles:
    news_df = pd.DataFrame(articles)
    news_df['sentiment'] = news_df['title'].map(sentiment)
    if len(news_df) >= 30:
        sa = round(float(news_df['sentiment'].mean()*100), 1)

scores = {'TA': ta, 'FA': fa, 'ON': on, 'SA': sa}
combined, coverage, conflicts = integral_score(scores)

st.subheader('Главная панель')
last_price = float(frame['close'].iloc[-1]) if frame is not None else None
prev_price = float(frame['close'].iloc[-2]) if frame is not None and len(frame)>1 else None
change = change_pct(last_price,prev_price) if last_price is not None and prev_price is not None else None
c1,c2,c3,c4 = st.columns(4)
c1.metric('ADA/USD', fmt_money(last_price), f'{change:+.2f}% / день' if change is not None else None)
c2.metric('Интегральная оценка', f'{combined:+.1f}' if combined is not None else 'Недоступна')
c3.metric('Полнота данных для оценки', f'{coverage:.0f}%')
c4.metric('Дата анализа', datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC'))
st.caption('Полнота данных — доля доступных модулей с учётом весов, НЕ оценка точности прогноза. Оценки и пороги являются учебными эвристиками.')
if issues:
    with st.expander(f'⚠️ Ограничения источников ({len(issues)})', expanded=True):
        for issue in issues: st.warning(issue)

technical, fundamental, chain, moods, summary, archive = st.tabs(['📈 Технический', '🏛️ Фундаментальный', '🔗 Ончейн', '💬 Настроения', '🎯 Комплексная оценка', '🗄️ История'])
with technical:
    st.header('Технический анализ')
    if frame is None: st.error('Нет данных для построения графика.')
    else:
        st.write('Цены и скользящие средние')
        fig = go.Figure()
        for name in ['close','SMA20','SMA50','BB_upper','BB_lower']:
            fig.add_trace(go.Scatter(x=frame['date'],y=frame[name],mode='lines',name=name))
        fig.update_layout(height=420, xaxis_title='Дата', yaxis_title='USD', legend_orientation='h')
        st.plotly_chart(fig, use_container_width=True)
        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=frame['date'],y=frame['RSI14'],name='RSI14'))
        f2.add_hline(y=70,line_dash='dash'); f2.add_hline(y=30,line_dash='dash')
        f2.update_layout(height=260,yaxis_title='RSI')
        st.plotly_chart(f2, use_container_width=True)
        f3 = go.Figure()
        f3.add_trace(go.Scatter(x=frame['date'], y=frame['MACD'],name='MACD'))
        f3.add_trace(go.Scatter(x=frame['date'],y=frame['MACD_signal'],name='Signal'))
        f3.update_layout(height=260)
        st.plotly_chart(f3, use_container_width=True)
        st.metric('Технический балл (-100…100)', ta if ta is not None else 'Нет данных')
        for x in ta_signals: st.write('•',x)
        st.download_button('Скачать обработанные цены (CSV)',frame.to_csv(index=False).encode('utf-8-sig'),'ada_indicators.csv','text/csv')
        st.dataframe(frame.tail(40).sort_values('date',ascending=False),use_container_width=True)
with fundamental:
    st.header('Фундаментальный анализ')
    st.write('ADA используется для комиссий и стейкинга в сети Cardano; оценка ниже основана только на числовых источниках, без субъективных оценок технологии.')
    if detail:
        m = detail.get('market_data') or {}
        cols = st.columns(3)
        cols[0].metric('Market Cap, USD', f"${(m.get('market_cap') or {}).get('usd',0):,.0f}")
        cols[1].metric('FDV, USD', f"${(m.get('fully_diluted_valuation') or {}).get('usd',0):,.0f}")
        cols[2].metric('Предложение ADA',f"{m.get('circulating_supply') or 0:,.0f}")
        st.write('Максимальное предложение:',m.get('max_supply'))
    if defi: st.metric('Cardano DeFi TVL',f"${defi.get('tvl',0):,.0f}")
    st.metric('Фундаментальный балл (-100…100)',f'{fa:+.1f}' if fa is not None else 'Недостаточно данных')
    for x in fa_factors: st.write('•',x)
    st.caption('Пороговые значения заданы разработчиком для демонстрации, не являются общепринятым инвестиционным стандартом.')
with chain:
    st.header('Ончейн-анализ')
    if onchain:
        st.write('Источник: Blockfrost, сеть Cardano mainnet.')
        cols = st.columns(3)
        cols[0].metric('Номер эпохи',onchain.get('epoch') or '—')
        cols[1].metric('Транзакции за эпоху',onchain.get('epoch_tx_count') or '—')
        fees = onchain.get('epoch_fees_lovelace')
        cols[2].metric('Комиссии за эпоху (ADA)', f'{int(fees)/1e6:,.0f}' if fees else '—')
        stake = onchain.get('epoch_active_stake_lovelace')
        st.write('Активный стейк (ADA):',f'{int(stake)/1e6:,.0f}' if stake else 'Нет данных')
        st.json(onchain)
    else: st.info('Для этого раздела нужен бесплатный ключ Blockfrost. Добавьте BLOCKFROST_PROJECT_ID.')
    for x in on_factors: st.info(x)
    st.warning('Ончейн-балл не рассчитывается по одному снимку: отсутствует историческая динамика. Это честно снижает полноту анализа.')
with moods:
    st.header('Анализ информационного фона')
    if news_df is None: st.warning('Не удалось получить публикации Cardano.')
    else:
        st.metric('Публикаций Cardano',len(news_df))
        counts = news_df['sentiment'].value_counts()
        labels = {-1:'Негативные',0:'Нейтральные',1:'Позитивные'}
        fig = go.Figure(go.Bar(x=[labels[k] for k in [-1,0,1]],y=[int(counts.get(k,0)) for k in [-1,0,1]]))
        st.plotly_chart(fig,use_container_width=True)
        st.metric('Индекс настроений (-100…100)',f'{sa:+.1f}' if sa is not None else 'Недостаточно публикаций (<30)')
        st.caption('Прозрачная словарная классификация английских заголовков. Не распознаёт надёжно сарказм и контекст. Рекомендуется ручная проверка не менее 20% материалов.')
        st.dataframe(news_df,use_container_width=True, column_config={'url':st.column_config.LinkColumn('Источник')})
        st.download_button('Скачать публикации (CSV)',news_df.to_csv(index=False).encode('utf-8-sig'),'ada_news.csv','text/csv')
with summary:
    st.header('Комплексная оценка Cardano')
    scores_df = pd.DataFrame([{'Модуль':name,'Балл':score,'Вес':w} for name,score,w in [('TA',ta,.30),('FA',fa,.25),('ON',on,.25),('SA',sa,.20)]])
    st.dataframe(scores_df,use_container_width=True,hide_index=True)
    st.write('**Формула:** S = 0,30·TA + 0,25·FA + 0,25·ON + 0,20·SA')
    st.subheader(explain(combined))
    st.write('Интегральный балл:',combined if combined is not None else 'Не формируется при отсутствии одного или нескольких модулей')
    st.write('Полнота:',f'{coverage:.0f}%')
    if conflicts:
        for x in conflicts: st.warning('Противоречие: '+x)
    else: st.info('Среди модулей с доступными баллами выраженных конфликтов нет.')
    st.caption('Это аналитический учебный инструмент, не инвестиционная рекомендация.')
    if st.button('💾 Сохранить этот расчёт в историю'):
        save_run(days, {'scores':scores,'integral':combined,'coverage':coverage,'issues':issues,'conflicts':conflicts,'price':last_price,'date':str(frame['date'].iloc[-1]) if frame is not None else None})
        st.success('Расчёт сохранён в SQLite.')
with archive:
    st.header('История анализа')
    rows = history()
    if rows.empty: st.info('История пока пуста. Нажмите «Сохранить этот расчёт» в разделе комплексной оценки.')
    else:
        parsed = rows.copy(); parsed['data']=parsed['data'].apply(json.loads)
        parsed['integral']=parsed['data'].apply(lambda x:x.get('integral'))
        parsed['coverage']=parsed['data'].apply(lambda x:x.get('coverage'))
        parsed['price']=parsed['data'].apply(lambda x:x.get('price'))
        st.dataframe(parsed.drop(columns=['data']),use_container_width=True)
        st.download_button('Экспорт истории (CSV)',parsed.drop(columns=['data']).to_csv(index=False).encode('utf-8-sig'),'history.csv','text/csv')
