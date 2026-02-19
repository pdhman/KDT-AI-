from __future__ import annotations
import pandas as pd

def period_returns_from_equity(equity: pd.Series, freq: str) -> pd.Series:
    """
    Period returns from equity curve.
    freq: 'M' (month), 'Y' (year)
    Return = (last equity in period / first equity in period) - 1
    """
    g = equity.groupby(equity.index.to_period(freq))
    ret = g.apply(lambda x: x.iloc[-1] / x.iloc[0] - 1.0)
    ret.index = ret.index.astype(str)
    return ret

def period_mdd_from_equity(equity: pd.Series, freq: str) -> pd.Series:
    """
    Period MDD (max drawdown) within each period computed from equity curve.
    freq: 'M' (month), 'Y' (year)
    """
    def _mdd(x: pd.Series) -> float:
        peak = x.cummax()
        dd = x / peak - 1.0
        return float(dd.min())

    g = equity.groupby(equity.index.to_period(freq))
    mdd = g.apply(_mdd)
    mdd.index = mdd.index.astype(str)
    return mdd
