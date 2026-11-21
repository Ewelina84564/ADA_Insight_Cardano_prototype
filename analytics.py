"""Pure, testable financial/aggregation computations for ADA Insight."""
from __future__ import annotations
import numpy as np
import pandas as pd


def indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Historical daily closing prices and volumes; no look-ahead."""
    df = frame.sort_values('date').copy()
    close = pd.to_numeric(df['close'], errors='coerce')
    df['SMA20'] = close.rolling(20, min_periods=20).mean()
    df['SMA50'] = close.rolling(50, min_periods=50).mean()
    df['EMA12'] = close.ewm(span=12, adjust=False).mean()
    df['EMA26'] = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']
    delta = close.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    avg_up = up.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_down = down.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_down == 0) & (avg_up > 0), 100)
    rsi = rsi.mask((avg_down == 0) & (avg_up == 0), 50)
    df['RSI14'] = rsi
    sd = close.rolling(20, min_periods=20).std(ddof=0)
    df['BB_upper'] = df['SMA20'] + 2 * sd
    df['BB_lower'] = df['SMA20'] - 2 * sd
    return df


def technical_score(df: pd.DataFrame) -> tuple[float|None, list[str]]:
    if len(df) < 35 or not pd.notna(df.iloc[-1]['RSI14']):
        return None, ['Недостаточно исторических данных для технического анализа.']
    x = df.iloc[-1]
    signals: list[tuple[float, str]] = []
    if pd.notna(x['SMA20']):
        signals.append((25 if x['close'] > x['SMA20'] else -25, 'Цена выше SMA20' if x['close'] > x['SMA20'] else 'Цена ниже SMA20'))
    signals.append((25 if x['MACD'] > x['MACD_signal'] else -25, 'MACD выше сигнальной линии' if x['MACD'] > x['MACD_signal'] else 'MACD ниже сигнальной линии'))
    rsi = float(x['RSI14'])
    signals.append((-25 if rsi > 70 else 25 if rsi < 30 else 0, f'RSI14 = {rsi:.1f}'))
    if pd.notna(x['SMA50']):
        signals.append((25 if x['SMA20'] > x['SMA50'] else -25, 'SMA20 выше SMA50' if x['SMA20'] > x['SMA50'] else 'SMA20 ниже SMA50'))
    return round(sum(s for s, _ in signals), 1), [message for _, message in signals]


def change_pct(new: float, old: float) -> float | None:
    if old is None or old == 0:
        return None
    return (new / old - 1) * 100


def integral_score(scores: dict[str, float | None], weights: dict[str, float] | None = None) -> tuple[float|None, float, list[str]]:
    """No confident combined conclusion if modules missing. Confidence is completeness proxy."""
    weights = weights or {'TA': .30, 'FA': .25, 'ON': .25, 'SA': .20}
    present = {name: value for name, value in scores.items() if value is not None and np.isfinite(value)}
    coverage = sum(weights[k] for k in present)
    conflicts = []
    keys = list(present)
    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            if present[a] >= 20 and present[b] <= -20 or present[b] >= 20 and present[a] <= -20:
                conflicts.append(f'{a} и {b} дают противоположные сигналы ({present[a]:+.0f} / {present[b]:+.0f}).')
    if coverage < .99:
        return None, round(coverage*100), conflicts
    return round(sum(weights[k]*present[k] for k in weights), 1), round(coverage*100), conflicts


def explain(score: float | None) -> str:
    if score is None:
        return 'Недостаточно данных для комплексной оценки'
    if score >= 30: return 'Преимущественно положительные сигналы'
    if score >= 10: return 'Умеренно положительная оценка'
    if score > -10: return 'Нейтральное состояние'
    if score > -30: return 'Умеренно отрицательная оценка'
    return 'Преимущественно отрицательные сигналы'


def onchain_score(epochs: pd.DataFrame) -> tuple[float | None, list[str]]:
    """Compare averages of recent 3 and previous 3 FINISHED epochs.
    Missing metric does not become neutral signal. Returns unavailable if less than 6 epochs.
    """
    if epochs is None or len(epochs) < 6:
        return None, ['Для сравнения требуется не менее 6 завершённых эпох Cardano.']
    df = epochs.sort_values('epoch').tail(6)
    factors = []
    explanations = []
    for col, label in [('tx_count','Число транзакций'),('fees_ada','Сетевые комиссии'),('active_stake_ada','Активный стейк')]:
        if col not in df: continue
        vals = pd.to_numeric(df[col], errors='coerce')
        before, after = vals.iloc[:3].mean(), vals.iloc[3:].mean()
        if not (np.isfinite(before) and np.isfinite(after) and before > 0): continue
        change = (after / before - 1) * 100
        factors.append(1 if change > 3 else -1 if change < -3 else 0)
        explanations.append(f'{label}: {change:+.1f}% (3 последние эпохи против 3 предыдущих; порог ±3%).')
    if len(factors) < 3:
        return None, explanations + ['Недостаточно трёх сопоставимых ончейн-показателей.']
    return round(100*sum(factors)/len(factors),1), explanations
