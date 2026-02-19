from __future__ import annotations
import pandas as pd
import numpy as np
from .portfolio import Portfolio, Position

def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)

def _cost_oneway(notional: float, fee_oneway: float, slip_oneway: float) -> float:
    return abs(notional) * (float(fee_oneway) + float(slip_oneway))

def _is_reentry_banned(pf: Portfolio, ticker: str, exec_date: pd.Timestamp, reentry_ban_months: int) -> bool:
    if reentry_ban_months <= 0:
        return False
    last_exit = pf.last_exit_exec_date.get(ticker)
    if last_exit is None:
        return False
    return _months_between(last_exit, exec_date) < reentry_ban_months

def rebalance_equal_weight(
    pf: Portfolio,
    exec_date: pd.Timestamp,
    exec_prices: pd.Series,
    target_tickers: list[str],
    max_positions: int,
    fee_oneway: float,
    slip_oneway: float,
    min_hold_months: int,
    reentry_ban_months: int,
    exposure: float = 1.0,
) -> None:
    exposure = max(0.0, min(1.0, float(exposure)))

    protected, sellable = [], []
    for t, pos in pf.positions.items():
        months = _months_between(pos.entry_exec_date, exec_date)
        (protected if months < min_hold_months else sellable).append(t)

    target_unique = list(dict.fromkeys(target_tickers))
    final = [t for t in protected if t in exec_prices.index and not pd.isna(exec_prices[t])]

    for t in target_unique:
        if t in final:
            continue
        if len(final) >= max_positions:
            break
        if t not in exec_prices.index or pd.isna(exec_prices[t]):
            continue
        if _is_reentry_banned(pf, t, exec_date, reentry_ban_months):
            continue
        final.append(t)

    traded = 0.0

    for t in list(pf.positions.keys()):
        if t in final or t not in sellable:
            continue
        px = float(exec_prices.get(t, np.nan))
        if pd.isna(px) or px <= 0:
            continue
        pos = pf.positions[t]
        notional = pos.shares * px
        pf.cash += notional - _cost_oneway(notional, fee_oneway, slip_oneway)
        traded += abs(notional)
        del pf.positions[t]
        pf.last_exit_exec_date[t] = exec_date

    total_val = pf.total_value(exec_prices)
    invest_target = total_val * exposure

    if not final:
        pf.record_traded(exec_date, traded)
        return

    target_per = invest_target / len(final)

    for t in final:
        px = float(exec_prices.get(t, np.nan))
        if pd.isna(px) or px <= 0:
            continue
        cur_shares = pf.positions[t].shares if t in pf.positions else 0.0
        cur_val = cur_shares * px
        diff = target_per - cur_val

        if abs(diff) < 1e-6:
            continue

        if diff > 0:
            cost_rate = float(fee_oneway) + float(slip_oneway)
            cash_need = diff * (1.0 + cost_rate)
            if cash_need > pf.cash and pf.cash > 0:
                diff = pf.cash / (1.0 + cost_rate)
                cash_need = diff * (1.0 + cost_rate)
            shares = diff / px
            if shares <= 0:
                continue
            pf.cash -= cash_need
            traded += abs(diff)
            if t in pf.positions:
                pf.positions[t].shares += shares
            else:
                pf.positions[t] = Position(shares=shares, entry_exec_date=exec_date)
        else:
            sell_val = -diff
            shares = min(cur_shares, sell_val / px)
            if shares <= 0:
                continue
            notional = shares * px
            pf.cash += notional - _cost_oneway(notional, fee_oneway, slip_oneway)
            traded += abs(notional)
            pf.positions[t].shares -= shares
            if pf.positions[t].shares <= 1e-12:
                del pf.positions[t]
                pf.last_exit_exec_date[t] = exec_date

    pf.record_traded(exec_date, traded)
