from __future__ import annotations
import pandas as pd

def month_end_dates(trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(trading_days, index=trading_days)
    me = s.groupby(pd.Grouper(freq="ME")).last().dropna()
    return pd.DatetimeIndex(me.values)

def week_end_dates(trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(trading_days, index=trading_days)
    we = s.groupby(pd.Grouper(freq="W-FRI")).last().dropna()
    return pd.DatetimeIndex(we.values)

def next_trading_day_map(trading_days: pd.DatetimeIndex) -> dict[pd.Timestamp, pd.Timestamp]:
    td = pd.DatetimeIndex(trading_days)
    return {td[i]: td[i+1] for i in range(len(td)-1)}

def build_signal_execution_pairs(trading_days: pd.DatetimeIndex, freq: str="monthly") -> pd.DataFrame:
    if freq not in ("monthly","weekly"):
        raise ValueError("freq must be 'monthly' or 'weekly'")
    td = pd.DatetimeIndex(trading_days)

    if freq == "monthly":
        me = month_end_dates(td)
        s = pd.Series(td, index=td)
        ms = s.groupby(pd.Grouper(freq="MS")).first().dropna()
        ms = pd.DatetimeIndex(ms.values)
        pairs = []
        for d in me:
            next_month = (d + pd.offsets.MonthBegin(1)).normalize()
            exec_candidates = ms[ms >= next_month]
            if len(exec_candidates) == 0:
                continue
            pairs.append((d, exec_candidates[0]))
        return pd.DataFrame(pairs, columns=["signal_date","exec_date"]).set_index("signal_date")

    we = week_end_dates(td)
    nxt = next_trading_day_map(td)
    pairs = []
    for d in we:
        ed = nxt.get(d, pd.NaT)
        if pd.isna(ed):
            continue
        pairs.append((d, ed))
    return pd.DataFrame(pairs, columns=["signal_date","exec_date"]).set_index("signal_date")
