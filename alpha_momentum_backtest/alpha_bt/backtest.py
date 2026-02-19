from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import numpy as np

from .calendar_utils import build_signal_execution_pairs, month_end_dates
from .indicators.momentum import to_month_end_prices, mixed_momentum
from .engine.portfolio import Portfolio
from .engine.execution import rebalance_equal_weight

@dataclass
class BacktestResult:
    equity: pd.Series
    traded_notional: pd.Series
    returns: pd.Series
    holdings_snapshots: dict[pd.Timestamp, list[str]]
    meta: dict

def _compute_ma(series: pd.Series, window: int = 200) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()

def run_backtest(
    prices: pd.DataFrame,
    start: str,
    end: str,
    N: int,
    w: float,
    rebalance_freq: str,
    fee_oneway: float,
    slip_oneway: float,
    initial_capital: float,
    min_hold_months: int,
    reentry_ban_months: int,
    regime: str = "none",
    market_close: pd.Series | None = None,
    risk_off_exposure: float = 0.5,
) -> BacktestResult:
    """
    B안: Daily mark-to-market equity recording.
    - Trades occur only on exec_date (rebalance day).
    - Equity is recorded for every trading day (accurate MDD/period MDD).
    """
    prices = prices.sort_index()
    prices = prices.loc[pd.to_datetime(start):pd.to_datetime(end)].copy()
    prices = prices.ffill()

    td = pd.DatetimeIndex(prices.index)
    pairs = build_signal_execution_pairs(td, freq=rebalance_freq)  # index=signal_date, col=exec_date

    # Map exec_date -> signal_date (unique)
    exec_to_signal: dict[pd.Timestamp, pd.Timestamp] = {}
    for sdt, row in pairs.iterrows():
        edt = pd.Timestamp(row["exec_date"])
        exec_to_signal[edt] = pd.Timestamp(sdt)

    # Momentum computed on month-end; use latest month-end <= signal_date
    me = month_end_dates(td)
    month_end_px = to_month_end_prices(prices, me)
    score_me = mixed_momentum(month_end_px, w=w)
    me_idx = score_me.index

    # Regime exposure per signal_date
    exposure_by_signal = {pd.Timestamp(d): 1.0 for d in pairs.index}
    if regime == "ma200":
        if market_close is None:
            raise ValueError("regime=ma200 requires market_close series")
        m = market_close.reindex(td).ffill()
        ma200 = _compute_ma(m, 200)
        for d in pairs.index:
            d = pd.Timestamp(d)
            close = m.get(d, np.nan)
            ma = ma200.get(d, np.nan)
            if pd.isna(close) or pd.isna(ma):
                exposure_by_signal[d] = 1.0
            else:
                exposure_by_signal[d] = float(risk_off_exposure) if close < ma else 1.0

    pf = Portfolio(initial_capital)
    holdings = {}

    for day in td:
        day = pd.Timestamp(day)

        # Execute rebalance if today is an exec_date
        if day in exec_to_signal:
            signal_date = exec_to_signal[day]

            candidates = me_idx[me_idx <= signal_date]
            if len(candidates) > 0:
                score_date = candidates[-1]
                s = score_me.loc[score_date].dropna()
                if not s.empty:
                    top = s.sort_values(ascending=False).head(N).index.tolist()
                    exec_prices = prices.loc[day]
                    exposure = exposure_by_signal.get(signal_date, 1.0)

                    rebalance_equal_weight(
                        pf=pf,
                        exec_date=day,
                        exec_prices=exec_prices,
                        target_tickers=top,
                        max_positions=N,
                        fee_oneway=fee_oneway,
                        slip_oneway=slip_oneway,
                        min_hold_months=min_hold_months,
                        reentry_ban_months=reentry_ban_months,
                        exposure=exposure,
                    )
                    holdings[day] = sorted(list(pf.positions.keys()))
                else:
                    pf.record_traded(day, 0.0)
            else:
                pf.record_traded(day, 0.0)

        # Daily mark-to-market record
        pf.record(day, prices.loc[day])

    equity = pd.Series([v for _, v in pf.value_history], index=[d for d, _ in pf.value_history], name="equity").sort_index()
    traded = pd.Series([v for _, v in pf.traded_notional_history], index=[d for d, _ in pf.traded_notional_history], name="traded_notional").sort_index()
    rets = equity.pct_change().dropna()

    meta = {
        "N": int(N), "w": float(w), "rebalance_freq": rebalance_freq,
        "fee_oneway": float(fee_oneway), "slip_oneway": float(slip_oneway),
        "min_hold_months": int(min_hold_months), "reentry_ban_months": int(reentry_ban_months),
        "regime": regime, "risk_off_exposure": float(risk_off_exposure),
        "equity_recording": "daily_mtm",
    }
    return BacktestResult(equity=equity, traded_notional=traded, returns=rets, holdings_snapshots=holdings, meta=meta)
