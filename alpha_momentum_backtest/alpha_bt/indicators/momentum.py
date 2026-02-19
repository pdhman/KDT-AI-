from __future__ import annotations
import pandas as pd

def to_month_end_prices(prices: pd.DataFrame, month_end_dates: pd.DatetimeIndex) -> pd.DataFrame:
    return prices.reindex(pd.DatetimeIndex(month_end_dates))

def momentum_lookback_skip1(month_end_px: pd.DataFrame, lookback_months: int) -> pd.DataFrame:
    px_t1 = month_end_px.shift(1)
    px_tk = month_end_px.shift(lookback_months)
    return (px_t1 / px_tk) - 1.0

def mixed_momentum(month_end_px: pd.DataFrame, w: float = 0.5) -> pd.DataFrame:
    w = float(w)
    if not (0.0 <= w <= 1.0):
        raise ValueError("w must be in [0,1]")
    mom_6_1 = momentum_lookback_skip1(month_end_px, 6)
    mom_12_1 = momentum_lookback_skip1(month_end_px, 12)
    return w * mom_6_1 + (1.0 - w) * mom_12_1
