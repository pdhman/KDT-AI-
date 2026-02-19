import argparse
from pathlib import Path
import pandas as pd

from alpha_bt.dataio import load_prices_panel
from alpha_bt.backtest import run_backtest
from alpha_bt.reports.metrics import summary
from alpha_bt.reports.export import save_json, save_series
from alpha_bt.reports.periodic import period_returns_from_equity, period_mdd_from_equity

def load_market_parquet(path: str) -> pd.Series:
    df = pd.read_parquet(path)
    s = df["close"] if "close" in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--N", type=int, default=8)
    ap.add_argument("--w", type=float, default=0.5)
    ap.add_argument("--rebalance", default="monthly", choices=["monthly","weekly"])
    ap.add_argument("--fee", type=float, default=0.0003)
    ap.add_argument("--slip", type=float, default=0.0)
    ap.add_argument("--min_hold", type=int, default=0)
    ap.add_argument("--reentry_ban", type=int, default=0)
    ap.add_argument("--regime", default="none", choices=["none","ma200"])
    ap.add_argument("--market", default=None)
    ap.add_argument("--risk_off_exposure", type=float, default=0.5)
    ap.add_argument("--initial", type=float, default=1_000_000_000.0)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    prices = load_prices_panel(args.prices)
    market = load_market_parquet(args.market) if args.market else None

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
        market_close=market,
        risk_off_exposure=args.risk_off_exposure,
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    stats = summary(res.equity, res.returns, res.traded_notional)
    stats.update(res.meta)
    save_json(stats, outdir / "summary.json")
    save_series(res.equity, outdir / "equity.csv")
    save_series(res.returns, outdir / "returns.csv")
    save_series(res.traded_notional, outdir / "traded_notional.csv")

    # Periodic returns & MDD from DAILY equity (B안)
    yret = period_returns_from_equity(res.equity, "Y")
    ymdd = period_mdd_from_equity(res.equity, "Y")
    mret = period_returns_from_equity(res.equity, "M")
    mmdd = period_mdd_from_equity(res.equity, "M")

    yret.to_csv(outdir / "yearly_returns.csv", header=True, encoding="utf-8-sig")
    ymdd.to_csv(outdir / "yearly_mdd.csv", header=True, encoding="utf-8-sig")
    mret.to_csv(outdir / "monthly_returns.csv", header=True, encoding="utf-8-sig")
    mmdd.to_csv(outdir / "monthly_mdd.csv", header=True, encoding="utf-8-sig")

    print("=== Summary ===")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"Saved periodic files in {outdir} (monthly/yearly returns & MDD)")

if __name__ == "__main__":
    main()
