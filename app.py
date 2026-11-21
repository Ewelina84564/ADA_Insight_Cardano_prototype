"""ADA Insight 2.0 – robust Streamlit Cloud educational dashboard."""
from __future__ import annotations
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analytics import indicators, technical_score, integral_score, explain, change_pct, onchain_score
from sources import market_data, defi_data, blockfrost_stats, news, sentiment

st.set_page_config(page_title='ADA Insight · Cardano', page_icon='🔷', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
.block-container {max-width:1280px;padding-top:1.2rem;}
[data-testid="stMetric"] {background:rgba(115,125,160,.08);padding:14px;border-radius:14px;border:1px solid rgba(130,140,165,.19);}
[data-testid="stSidebar"] {border-right:1px solid rgba(135,145,165,.18);}
</style>''',unsafe_allow_html=True)

DB=Path(__file__).with_name('ada_insight.sqlite3')
def num(value):
    try:
        if value is None: return None
        n=float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError,OverflowError): return None

def money(v,decimals=0):
    n=num(v)
    return f'${n:,.{decimals}f}' if n is not None else 'Нет данных'

def quantity(v,decimals=0):
    n=num(v)
    return f'{n:,.{decimals}f}' if n is not None else 'Нет данных'

@st.cache_data(ttl=900,show_spinner=False)
def load_market(days): return market_data(days)
@st.cache_data(ttl=1800,show_spinner=False)
def load_defi(): return defi_data()
@st.cache_data(ttl=1800,show_spinner=False)
def load_chain(key): return blockfrost_stats(key=key)
@st.cache_data(ttl=1800,show_spinner=False)
def load_news(): return news()

def load_data(days,key):
    results={'frame':None,'detail':None,'defi':None,'epochs':None,'articles':[],'issues':[],'loaded_at':datetime.now(timezone.utc).isoformat(),'days':days}
    try:
        results['frame'],results['detail'],warning=load_market(days)
        if warning: results['issues'].append(warning)
    except Exception as exc: results['issues'].append(f'CoinGecko: {type(exc).__name__}: {exc}')
    try: results['defi']=load_defi()
    except Exception as exc: results['issues'].append(f'DefiLlama: {type(exc).__name__}: {exc}')
    try:
        results['epochs'],warning=load_chain(key)
        if warning: results['issues'].append(warning)
    except Exception as exc: results['issues'].append(f'Blockfrost: {type(exc).__name__}: {exc}')
    try: results['articles']=load_news()
    except Exception as exc: results['issues'].append(f'Google News: {type(exc).__name__}: {exc}')
    return results

def init_db():
    try:
        with sqlite3.connect(DB,timeout=5) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, run_at TEXT NOT NULL, period INTEGER NOT NULL, payload TEXT NOT NULL)')
        return None
    except Exception as exc:
        return f'SQLite недоступна: {type(exc).__name__}: {exc}'

def save_run(days,payload):
    with sqlite3.connect(DB,timeout=5) as conn:
        conn.execute('INSERT INTO runs (run_at,period,payload) VALUES (?,?,?)',
            (datetime.now(timezone.utc).isoformat(),int(days),json.dumps(payload,ensure_ascii=False)))

def history():
    with sqlite3.connect(DB,timeout=5) as conn:
        return pd.read_sql_query('SELECT * FROM runs ORDER BY id DESC LIMIT 100',conn)

st.title('🔷 ADA Insight')
st.caption('Cardano (ADA/USD) · Технический, фундаментальный, ончейн-анализ и анализ настроений')
db_error=init_db()
with st.sidebar:
    st.header('⚙️ Настройки')
    days=st.selectbox('Период истории цены',[30,90,180,365],index=2,format_func=lambda d:f'{d} дней')
    key=''
    try: key=str(st.secrets.get('BLOCKFROST_PROJECT_ID','') or '').strip()
    except Exception: pass
    key=key or os.getenv('BLOCKFROST_PROJECT_ID','').strip()
    with st.expander('Ключ Blockfrost (необязательно)'):
        manual=st.text_input('Project ID',value='',type='password',help='Для личной проверки. Для опубликованного сайта лучше Streamlit → Settings → Secrets.')
        if manual: key=manual.strip()
        st.caption('Не записывайте секретные ключи в GitHub.')
    refresh=st.button('🔄 Загрузить / пересчитать',type='primary',use_container_width=True)
    if st.button('Очистить кэш данных',use_container_width=True):
        st.cache_data.clear()
        st.info('Кэш очищен. Теперь нажмите «Загрузить / пересчитать».')
    st.caption('Источник цены — CoinGecko; DeFi — DefiLlama; сеть — Blockfrost; новости — Google News.')
    st.caption('Учебная аналитика, не инвестиционная рекомендация.')

if refresh:
    with st.spinner('Получаем данные из внешних API. Если источник недоступен, остальные разделы продолжат работать…'):
        st.session_state['ada_analysis']=load_data(days,key)
        st.session_state['ada_key_present']=bool(key)

if 'ada_analysis' not in st.session_state:
    st.info('👋 Сайт успешно запущен! Нажмите **«🔄 Загрузить / пересчитать»** слева, чтобы получить реальные данные Cardano. Без ключа Blockfrost ончейн-оценка будет недоступна.')
    st.subheader('Модули аналитической системы')
    a,b,c,d=st.columns(4)
    a.info('📈 **Технический**\n\nRSI · MACD · EMA · SMA')
    b.info('🏛️ **Фундаментальный**\n\nРыночная оценка · токеномика')
    c.info('🔗 **Ончейн**\n\nТранзакции · комиссии · стейкинг')
    d.info('💬 **Настроения**\n\nПубликации · тональность')
    st.stop()

raw=st.session_state['ada_analysis']
frame=raw.get('frame'); detail=raw.get('detail'); defi=raw.get('defi'); epochs=raw.get('epochs'); articles=raw.get('articles') or []
issues=list(raw.get('issues') or [])
if frame is not None and not frame.empty:
    frame=indicators(frame)
    ta,ta_factors=technical_score(frame)
else:
    frame=None; ta=None; ta_factors=['Нет исторических рыночных данных.']

market=(detail or {}).get('market_data') or {}
cap=num((market.get('market_cap') or {}).get('usd'))
fdv=num((market.get('fully_diluted_valuation') or {}).get('usd'))
circ=num(market.get('circulating_supply'))
max_supply=num(market.get('max_supply'))
tvl=num((defi or {}).get('tvl'))
fa_factors=[]; criteria=[]
if cap and fdv and fdv>0:
    ratio=cap/fdv; criteria.append(1 if ratio>=.75 else -1)
    fa_factors.append(f'Market Cap / FDV = {ratio:.2f}; критерий: ≥ 0,75.')
if circ is not None and max_supply and max_supply>0:
    ratio=circ/max_supply; criteria.append(1 if ratio>=.75 else -1)
    fa_factors.append(f'Циркулирует {ratio:.1%} максимального предложения; критерий: ≥ 75%.')
if cap and tvl is not None:
    ratio=tvl/cap; criteria.append(1 if ratio>=.05 else -1)
    fa_factors.append(f'TVL / капитализация = {ratio:.2%}; учебный критерий: ≥ 5%.')
fa=round(100*sum(criteria)/3,1) if len(criteria)==3 else None
if fa is None: fa_factors.append('Для фундаментального балла необходимы все три сравнения.')

chain_df=pd.DataFrame(epochs) if epochs else None
on,on_factors=onchain_score(chain_df)

news_df=pd.DataFrame(articles) if articles else None
sa=None
if news_df is not None:
    news_df['sentiment']=news_df['title'].map(sentiment)
    if len(news_df)>=30: sa=round(float(news_df['sentiment'].mean())*100,1)

scores={'TA':ta,'FA':fa,'ON':on,'SA':sa}
combined,coverage,conflicts=integral_score(scores)
last=num(frame['close'].iloc[-1]) if frame is not None else None
prev=num(frame['close'].iloc[-2]) if frame is not None and len(frame)>1 else None
change=change_pct(last,prev) if last is not None and prev is not None else None

st.subheader('📌 Главная панель')
c1,c2,c3,c4=st.columns(4)
c1.metric('ADA / USD',money(last,4),f'{change:+.2f}% / день' if change is not None else None)
c2.metric('Интегральная оценка',f'{combined:+.1f}' if combined is not None else 'Недоступна')
c3.metric('Полнота оценочных данных',f'{coverage:.0f}%')
c4.metric('Обновлено (UTC)',str(raw.get('loaded_at',''))[:16].replace('T',' '))
st.caption('Полнота — сумма весов модулей с рассчитанными баллами, НЕ вероятность верного прогноза. Для интегральной оценки нужны все 4 модуля.')
if issues:
    with st.expander(f'⚠️ Ограничения / ошибки источников ({len(issues)})',expanded=True):
        for issue in issues: st.warning(issue)
if db_error: st.warning(db_error)

t1,t2,t3,t4,t5,t6=st.tabs(['📈 Технический','🏛️ Фундаментальный','🔗 Ончейн','💬 Настроения','🎯 Комплексная оценка','🗄️ История'])
with t1:
    st.header('Технический анализ')
    if frame is None: st.error('История ADA недоступна. Проверьте ответ CoinGecko и повторите загрузку.')
    else:
        fig=go.Figure()
        for col in ['close','SMA20','SMA50','BB_upper','BB_lower']:
            fig.add_trace(go.Scatter(x=frame['date'],y=frame[col],mode='lines',name=col))
        fig.update_layout(height=390,xaxis_title='Дата',yaxis_title='USD',legend_orientation='h')
        st.plotly_chart(fig,use_container_width=True)
        f2=go.Figure(); f2.add_trace(go.Scatter(x=frame['date'],y=frame['RSI14'],name='RSI14'))
        f2.add_hline(y=70,line_dash='dash'); f2.add_hline(y=30,line_dash='dash')
        f2.update_layout(height=240)
        st.plotly_chart(f2,use_container_width=True)
        f3=go.Figure()
        for name in ['MACD','MACD_signal']:
            f3.add_trace(go.Scatter(x=frame['date'],y=frame[name],name=name))
        f3.update_layout(height=240)
        st.plotly_chart(f3,use_container_width=True)
        if 'volume' in frame:
            f4=go.Figure(go.Bar(x=frame['date'],y=frame['volume'],name='Объём'))
            f4.update_layout(height=230)
            st.plotly_chart(f4,use_container_width=True)
        st.metric('Технический балл',f'{ta:+.1f}' if ta is not None else 'Нет данных')
        for note in ta_factors: st.write('•',note)
        st.dataframe(frame.tail(30).sort_values('date',ascending=False),use_container_width=True)
        st.download_button('Скачать индикаторы CSV',frame.to_csv(index=False).encode('utf-8-sig'),'cardano_indicators.csv','text/csv')
with t2:
    st.header('Фундаментальный анализ')
    a,b,c=st.columns(3)
    a.metric('Капитализация',money(cap)); b.metric('FDV',money(fdv)); c.metric('DeFi TVL',money(tvl))
    d,e=st.columns(2)
    d.metric('Циркулирующее предложение',quantity(circ)); e.metric('Максимальное предложение',quantity(max_supply))
    st.metric('Фундаментальный балл',f'{fa:+.1f}' if fa is not None else 'Недостаточно данных')
    for note in fa_factors: st.write('•',note)
    st.caption('Три числовых критерия являются прозрачными учебными эвристиками, а не доказанной оценкой стоимости ADA.')
    with st.expander('Сырые данные CoinGecko и DefiLlama'):
        if detail: st.json({'market_data':market})
        if defi: st.json(defi)
with t3:
    st.header('Ончейн-анализ Cardano')
    if chain_df is None or chain_df.empty:
        st.info('Нет исторических эпох Cardano. Создайте Project ID Cardano mainnet на Blockfrost и добавьте его в Streamlit Secrets.')
    else:
        st.caption('Последние завершённые эпохи; текущая незавершённая эпоха исключена.')
        st.dataframe(chain_df.sort_values('epoch',ascending=False),use_container_width=True)
        for col,name in [('tx_count','Транзакции'),('fees_ada','Комиссии (ADA)'),('active_stake_ada','Активный стейк (ADA)')]:
            if col in chain_df:
                fig=go.Figure(go.Scatter(x=chain_df['epoch'],y=chain_df[col],mode='lines+markers',name=name))
                fig.update_layout(height=230,xaxis_title='Эпоха',yaxis_title=name)
                st.plotly_chart(fig,use_container_width=True)
        st.download_button('Скачать эпохи CSV',chain_df.to_csv(index=False).encode('utf-8-sig'),'cardano_epochs.csv','text/csv')
    st.metric('Ончейн-балл',f'{on:+.1f}' if on is not None else 'Недостаточно данных')
    for note in on_factors: st.write('•',note)
    st.caption('Баллы основаны на направлении изменений трёх метрик, не измеряют безопасность сети или цену токена.')
with t4:
    st.header('Анализ настроений о Cardano')
    if news_df is None or news_df.empty: st.warning('Публикации не получены.')
    else:
        st.metric('Получено публикаций',len(news_df))
        counts=news_df['sentiment'].value_counts()
        fig=go.Figure(go.Bar(x=['Негативные','Нейтральные','Позитивные'],y=[int(counts.get(v,0)) for v in [-1,0,1]]))
        st.plotly_chart(fig,use_container_width=True)
        if 'published' in news_df:
            tmp=news_df.copy();tmp['date']=pd.to_datetime(tmp['published'],errors='coerce',utc=True).dt.date
            daily=tmp.dropna(subset=['date']).groupby('date')['sentiment'].mean().reset_index()
            if not daily.empty:
                st.plotly_chart(go.Figure(go.Scatter(x=daily['date'],y=daily['sentiment'],mode='lines+markers',name='Средняя тональность')),use_container_width=True)
        st.metric('Индекс настроений',f'{sa:+.1f}' if sa is not None else 'Нужно ≥ 30 публикаций')
        st.dataframe(news_df,use_container_width=True)
        st.download_button('Скачать новости CSV',news_df.to_csv(index=False).encode('utf-8-sig'),'cardano_news.csv','text/csv')
        st.caption('Классификация словарная, по английским заголовкам; сарказм и отрицания могут классифицироваться неверно.')
with t5:
    st.header('Комплексная аналитическая оценка')
    st.dataframe(pd.DataFrame([{'Модуль':k,'Балл':v,'Вес':w} for k,v,w in [('TA',ta,.30),('FA',fa,.25),('ON',on,.25),('SA',sa,.20)]]),hide_index=True,use_container_width=True)
    st.write('**S = 0,30 × TA + 0,25 × FA + 0,25 × ON + 0,20 × SA**')
    st.subheader(explain(combined))
    st.write('Интегральный балл:',combined if combined is not None else 'Недостаточно данных — вывод не формируется')
    st.write('Полнота модулей:',f'{coverage:.0f}%')
    if conflicts:
        for c in conflicts: st.warning('Противоречие: '+c)
    else: st.info('Среди оценённых модулей резких противоположных сигналов не выявлено.')
    st.caption('Интерпретации и веса учебные. Полученный балл — не прогноз доходности.')
    if st.button('💾 Сохранить расчёт в историю'):
        if db_error: st.error(db_error)
        else:
            try:
                save_run(raw['days'],{'scores':scores,'integral':combined,'coverage':coverage,'price':last,'issues':issues,'at':raw['loaded_at']})
                st.success('Результат сохранён.')
            except Exception as exc: st.error(f'Не удалось сохранить: {exc}')
with t6:
    st.header('История анализа')
    st.caption('SQLite находится на сервере Streamlit и может сбрасываться при перезапуске/пересборке приложения. Для постоянного архива потребуется внешняя БД.')
    if db_error: st.error(db_error)
    else:
        try:
            rows=history()
            if rows.empty: st.info('История пока пуста. Сохраните расчёт на вкладке «Комплексная оценка».')
            else:
                st.dataframe(rows,use_container_width=True)
                st.download_button('Скачать историю CSV',rows.to_csv(index=False).encode('utf-8-sig'),'ada_history.csv','text/csv')
        except Exception as exc: st.error(f'Не удалось прочитать историю: {exc}')
