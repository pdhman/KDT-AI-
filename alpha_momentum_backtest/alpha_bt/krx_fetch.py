from __future__ import annotations
import pandas as pd
from tqdm import tqdm

try:
    from pykrx import stock
except Exception:
    stock = None

def _require_pykrx():
    if stock is None:
        raise ImportError("pykrx is required. Install with: pip install pykrx")

def fetch_adjusted_close_panel(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    _require_pykrx()
    panel = []
    for t in tqdm(tickers, desc="Fetching KRX adjusted prices"):
        df = stock.get_market_ohlcv_by_date(start, end, t, adjusted=True)
        s = df["종가"].rename(t)
        s.index = pd.to_datetime(s.index)
        panel.append(s)
    return pd.concat(panel, axis=1).sort_index()

def fetch_kospi200_index_close(start: str, end: str, index_ticker: str="1028") -> pd.Series:
    _require_pykrx()
    df = stock.get_index_ohlcv_by_date(start, end, index_ticker)
    s = df["종가"].copy()
    s.index = pd.to_datetime(s.index)
    s.name = "KOSPI200"
    return s

def build_universe_by_mcap(date: str, market: str="KOSPI", mcap_min: int=500_000_000_000) -> pd.DataFrame:
    _require_pykrx()
    cap = stock.get_market_cap_by_ticker(date, market=market)
    cap = cap.reset_index().rename(columns={"티커": "ticker"})
    mcap_col = next((c for c in cap.columns if "시가총액" in c), None)
    if mcap_col is None:
        raise RuntimeError("Could not find market cap column from pykrx output")
    cap["ticker"] = cap["ticker"].astype(str).str.zfill(6)
    name_col = next((c for c in cap.columns if "종목명" in c), None)
    if name_col is None:
        cap["name"] = ""
    else:
        cap = cap.rename(columns={name_col: "name"})
    cap = cap.rename(columns={mcap_col: "mcap"})
    cap = cap[cap["mcap"] >= mcap_min].sort_values("mcap", ascending=False)
    return cap[["ticker","name","mcap"]].reset_index(drop=True)
