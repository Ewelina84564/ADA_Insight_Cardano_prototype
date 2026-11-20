import numpy as np
import pandas as pd
from analytics import indicators, technical_score, integral_score

def test_sma():
    d = pd.DataFrame({'date':pd.date_range('2026-01-01',periods=60),'close':np.arange(1,61,dtype=float),'volume':np.ones(60)})
    out = indicators(d)
    assert np.isclose(out.iloc[-1]['SMA20'],50.5)
    assert np.isclose(out.iloc[-1]['EMA12'], 54.5, atol=.1)
    assert out.iloc[-1]['RSI14'] == 100
    assert technical_score(out)[0] is not None

def test_incomplete_integral():
    score, confidence, conflicts = integral_score({'TA':30,'FA':20,'ON':None,'SA':-40})
    assert score is None
    assert confidence == 75
    assert conflicts

def test_full_integral():
    score, confidence, _ = integral_score({'TA':100,'FA':0,'ON':-100,'SA':50})
    assert score == 15
    assert confidence == 100
