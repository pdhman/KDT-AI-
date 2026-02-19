from __future__ import annotations
import pandas as pd
from pathlib import Path

def read_universe_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        raise ValueError("universe.csv must have a 'ticker' column")
    df["ticker"] = df["ticker"].astype(str).str.replace("A", "", regex=False).str.zfill(6)
    return df

def save_prices_panel(prices: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(path, index=True)

def load_prices_panel(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return pd.read_parquet(path)
