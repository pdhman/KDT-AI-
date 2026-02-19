from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import numpy as np

@dataclass
class Position:
    shares: float
    entry_exec_date: pd.Timestamp

class Portfolio:
    def __init__(self, initial_capital: float):
        self.cash = float(initial_capital)
        self.positions: dict[str, Position] = {}
        self.value_history: list[tuple[pd.Timestamp, float]] = []
        self.traded_notional_history: list[tuple[pd.Timestamp, float]] = []
        self.last_exit_exec_date: dict[str, pd.Timestamp] = {}

    def market_value(self, prices_row: pd.Series) -> float:
        mv = 0.0
        for t, pos in self.positions.items():
            px = prices_row.get(t, np.nan)
            if pd.isna(px):
                continue
            mv += pos.shares * float(px)
        return mv

    def total_value(self, prices_row: pd.Series) -> float:
        return self.cash + self.market_value(prices_row)

    def record(self, date: pd.Timestamp, prices_row: pd.Series) -> None:
        self.value_history.append((date, self.total_value(prices_row)))

    def record_traded(self, date: pd.Timestamp, traded_notional: float) -> None:
        self.traded_notional_history.append((date, float(traded_notional)))
