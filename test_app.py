import math
import pandas as pd
from analytics import onchain_score
from sources import number, sentiment


def test_conversion_safe():
    assert number(None) is None
    assert number('invalid') is None
    assert number('nan') is None
    assert number('1000000',factor=1e6)==1


def test_onchain_missing():
    assert onchain_score(pd.DataFrame())[0] is None


def test_onchain_six_epochs():
    frame=pd.DataFrame({'epoch':range(6),'tx_count':[100,100,100,120,120,120],
                        'fees_ada':[100,100,100,120,120,120],
                        'active_stake_ada':[100,100,100,120,120,120]})
    result,_=onchain_score(frame)
    assert result==100


def test_sentiment():
    assert sentiment('Cardano gains after approval')==1
    assert sentiment('ADA hack warning')==-1
    assert sentiment('Cardano update')==0
