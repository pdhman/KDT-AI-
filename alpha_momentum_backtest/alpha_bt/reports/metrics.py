from __future__ import annotations
import pandas as pd
import numpy as np

def cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return float("nan")
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)

def mdd(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())

def sharpe_periodic(returns: pd.Series, periods_per_year: int) -> float:
    r = returns.dropna()
    if len(r) < 3:
        return float("nan")
    sd = r.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float((r.mean() / sd) * np.sqrt(periods_per_year))

def turnover_annual(traded_notional: pd.Series, equity: pd.Series) -> float:
    if traded_notional.empty or equity.empty:
        return float("nan")
    total = traded_notional.sum()
    avg = equity.mean()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    return float(total / avg / years)

def calmar(cagr_val: float, mdd_val: float) -> float:
    if mdd_val == 0 or np.isnan(mdd_val):
        return float("nan")
    return float(cagr_val / abs(mdd_val))

def _infer_ppy(returns: pd.Series) -> int:
    if len(returns) < 6:
        return 12
    deltas = np.diff(returns.index.values).astype("timedelta64[D]").astype(int)
    med = float(np.median(deltas))
    if med <= 3:
        return 252
    if med <= 8:
        return 52
    return 12

def summary(equity: pd.Series, returns: pd.Series, traded_notional: pd.Series) -> dict:
    C = cagr(equity)
    D = mdd(equity)
    ppy = _infer_ppy(returns)
    S = sharpe_periodic(returns, periods_per_year=ppy)
    T = turnover_annual(traded_notional, equity)
    return {
        "Total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
        "CAGR": float(C),
        "MDD": float(D),
        "Sharpe": float(S),
        "Turnover_annual": float(T),
        "Final_equity": float(equity.iloc[-1]),
        "Calmar": float(calmar(C, D)),
    }
