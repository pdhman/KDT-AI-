import argparse
from pathlib import Path
import pandas as pd

from alpha_bt.dataio import load_prices_panel
from alpha_bt.backtest import run_backtest
from alpha_bt.reports.metrics import summary

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
    ap.add_argument("--N_min", type=int, default=3)
    ap.add_argument("--N_max", type=int, default=10)
    ap.add_argument("--min_hold_min", type=int, default=0)
    ap.add_argument("--min_hold_max", type=int, default=6)
    ap.add_argument("--reentry_ban_min", type=int, default=0)
    ap.add_argument("--reentry_ban_max", type=int, default=6)
    ap.add_argument("--w", type=float, default=0.5)
    ap.add_argument("--rebalance", default="monthly", choices=["monthly","weekly"])
    ap.add_argument("--fee", type=float, default=0.0003)
    ap.add_argument("--slip", type=float, default=0.0)
    ap.add_argument("--regime", default="none", choices=["none","ma200"])
    ap.add_argument("--market", default=None)
    ap.add_argument("--risk_off_exposure", type=float, default=0.5)
    ap.add_argument("--initial", type=float, default=1_000_000_000.0)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    prices = load_prices_panel(args.prices)
    market = load_market_parquet(args.market) if args.market else None

    rows = []
    for N in range(args.N_min, args.N_max + 1):
        for mh in range(args.min_hold_min, args.min_hold_max + 1):
            for rb in range(args.reentry_ban_min, args.reentry_ban_max + 1):
                res = run_backtest(
                    prices=prices,
                    start=args.start,
                    end=args.end,
                    N=N,
                    w=args.w,
                    rebalance_freq=args.rebalance,
                    fee_oneway=args.fee,
                    slip_oneway=args.slip,
                    initial_capital=args.initial,
                    min_hold_months=mh,
                    reentry_ban_months=rb,
                    regime=args.regime,
                    market_close=market,
                    risk_off_exposure=args.risk_off_exposure,
                )
                stats = summary(res.equity, res.returns, res.traded_notional)
                rows.append({"N": N, "min_hold": mh, "reentry_ban": rb, **stats})
                print(f"Done N={N} min_hold={mh} reentry_ban={rb} Calmar={stats['Calmar']:.3f}")

    df = pd.DataFrame(rows)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df.to_csv(outdir / "grid_results.csv", index=False, encoding="utf-8-sig")
    df.sort_values("Calmar", ascending=False).head(10).to_csv(outdir / "top10_calmar.csv", index=False, encoding="utf-8-sig")

    df.groupby("N")[["CAGR","MDD","Sharpe","Turnover_annual","Calmar"]].mean().reset_index().to_csv(
        outdir / "sensitivity_by_N.csv", index=False, encoding="utf-8-sig"
    )
    df.groupby("min_hold")[["CAGR","MDD","Sharpe","Turnover_annual","Calmar"]].mean().reset_index().to_csv(
        outdir / "sensitivity_by_min_hold.csv", index=False, encoding="utf-8-sig"
    )
    df.groupby("reentry_ban")[["CAGR","MDD","Sharpe","Turnover_annual","Calmar"]].mean().reset_index().to_csv(
        outdir / "sensitivity_by_reentry_ban.csv", index=False, encoding="utf-8-sig"
    )

    print(f"Saved grid outputs to {outdir}")

if __name__ == "__main__":
    main()
