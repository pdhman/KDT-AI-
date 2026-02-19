# scripts/make_benchmark_plots.py
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

from alpha_bt.dataio import load_prices_panel
from alpha_bt.backtest import run_backtest

def load_market_close_parquet(path: str) -> pd.Series:
    df = pd.read_parquet(path)
    # 보통 close 컬럼이 있지만, 없으면 첫 번째 컬럼을 사용
    if isinstance(df, pd.Series):
        s = df
    else:
        s = df["close"] if "close" in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    s.name = "kospi200"
    return s.sort_index()

def compute_drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    dd.name = "drawdown"
    return dd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True, help="data/prices_top200.parquet")
    ap.add_argument("--market", required=True, help="data/kospi200_index_close.parquet")
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--N", type=int, default=10)
    ap.add_argument("--w", type=float, default=0.0)
    ap.add_argument("--rebalance", choices=["monthly", "weekly"], default="monthly")
    ap.add_argument("--fee", type=float, default=0.0015)
    ap.add_argument("--slip", type=float, default=0.0005)
    ap.add_argument("--min_hold", type=int, default=0)
    ap.add_argument("--reentry_ban", type=int, default=0)
    ap.add_argument("--regime", choices=["none", "ma200"], default="none")
    ap.add_argument("--risk_off_exposure", type=float, default=0.5)
    ap.add_argument("--initial", type=float, default=1_000_000_000.0)
    ap.add_argument("--outdir", required=True, help="e.g. outputs/benchmark/u200_base")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    figdir = outdir / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    # --- Load data ---
    prices = load_prices_panel(args.prices)
    market_close = load_market_close_parquet(args.market)

    # --- Run strategy backtest (v3: daily mark-to-market equity) ---
    res = run_backtest(
        prices=prices,
        start=args.start,
        end=args.end,
        N=args.N,
        w=args.w,
        rebalance_freq=args.rebalance,
        fee_oneway=args.fee,
        slip_oneway=args.slip,
        initial_capital=args.initial,
        min_hold_months=args.min_hold,
        reentry_ban_months=args.reentry_ban,
        regime=args.regime,
        market_close=market_close if args.regime == "ma200" else None,
        risk_off_exposure=args.risk_off_exposure,
    )
    strat_eq = res.equity.copy()
    strat_eq.name = "strategy"

    # --- Build benchmark equity (normalize market close) ---
    m = market_close.loc[strat_eq.index.min():strat_eq.index.max()].copy()
    df = pd.concat([strat_eq, m], axis=1, join="inner").dropna()
    df.columns = ["strategy", "kospi200"]

    # Normalize to 1.0 at start
    df_norm = df / df.iloc[0]

    # Save normalized series (optional, useful for debugging/PPT)
    df_norm.to_csv(outdir / "equity_strategy_vs_kospi200.csv", encoding="utf-8-sig")

    # --- Plot 1: Equity curves ---
    plt.figure(figsize=(10, 5))
    plt.plot(df_norm.index, df_norm["strategy"], label="Strategy", linewidth=2)
    plt.plot(df_norm.index, df_norm["kospi200"], label="KOSPI200", linestyle="--")
    plt.title("Equity Curve (Normalized): Strategy vs KOSPI200")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(figdir / "equity_vs_kospi200.png", dpi=160)
    plt.close()

    # --- Plot 2: Drawdown curves ---
    dd_s = compute_drawdown(df_norm["strategy"])
    dd_m = compute_drawdown(df_norm["kospi200"])

    plt.figure(figsize=(10, 5))
    plt.plot(dd_s.index, dd_s, label="Strategy", linewidth=2)
    plt.plot(dd_m.index, dd_m, label="KOSPI200", linestyle="--")
    plt.axhline(0.0, linewidth=0.8)
    plt.title("Drawdown Curve: Strategy vs KOSPI200")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(figdir / "drawdown_vs_kospi200.png", dpi=160)
    plt.close()

    # --- Plot 3: Combined Equity (top) + Drawdown (bottom) ---
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]}
    )

    # Top: Equity
    ax1.plot(df_norm.index, df_norm["strategy"], label="Strategy", linewidth=2)
    ax1.plot(df_norm.index, df_norm["kospi200"], label="KOSPI200", linestyle="--")
    ax1.set_title("Equity & Drawdown: Strategy vs KOSPI200")
    ax1.set_ylabel("Normalized Equity (Start = 1.0)")
    ax1.legend()
    ax1.grid(True)

    # Bottom: Drawdown
    dd_s = compute_drawdown(df_norm["strategy"])
    dd_m = compute_drawdown(df_norm["kospi200"])

    ax2.plot(dd_s.index, dd_s, label="Strategy", linewidth=2)
    ax2.plot(dd_m.index, dd_m, label="KOSPI200", linestyle="--")
    ax2.axhline(0.0, linewidth=0.8)
    ax2.set_ylabel("Drawdown")
    ax2.set_xlabel("Date")
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig(figdir / "equity_drawdown_combined.png", dpi=160)
    plt.close()

    # Save drawdown series
    pd.concat([dd_s.rename("strategy_dd"), dd_m.rename("kospi200_dd")], axis=1)\
      .to_csv(outdir / "drawdown_strategy_vs_kospi200.csv", encoding="utf-8-sig")

    print("Saved:")
    print(f"- {figdir / 'equity_vs_kospi200.png'}")
    print(f"- {figdir / 'drawdown_vs_kospi200.png'}")
    print(f"- {figdir / 'equity_drawdown_combined.png'}")
    print(f"- {outdir / 'equity_strategy_vs_kospi200.csv'}")
    print(f"- {outdir / 'drawdown_strategy_vs_kospi200.csv'}")

   
if __name__ == "__main__":
    main()
