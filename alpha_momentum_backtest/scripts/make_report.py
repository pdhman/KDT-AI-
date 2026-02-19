import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def _read_json(p: Path) -> dict:
    import json
    return json.loads(p.read_text(encoding="utf-8"))

def read_summary(run_dir: Path) -> dict:
    return _read_json(run_dir / "summary.json")

def read_equity(run_dir: Path) -> pd.Series:
    df = pd.read_csv(run_dir / "equity.csv")
    df.iloc[:,0] = pd.to_datetime(df.iloc[:,0])
    return pd.Series(df.iloc[:,1].values, index=df.iloc[:,0], name=run_dir.name)

def make_summary_table(run_dirs: list[Path]) -> pd.DataFrame:
    rows = []
    for d in run_dirs:
        s = read_summary(d)
        s["run"] = d.name
        rows.append(s)
    df = pd.DataFrame(rows)
    front = ["run","CAGR","MDD","Calmar","Sharpe","Turnover_annual","Total_return","Final_equity",
             "N","w","rebalance_freq","fee_oneway","slip_oneway","min_hold_months","reentry_ban_months","regime","risk_off_exposure"]
    cols = [c for c in front if c in df.columns] + [c for c in df.columns if c not in front]
    return df[cols]

def plot_equity_curves(equities: list[pd.Series], outpath: Path) -> None:
    plt.figure()
    for s in equities:
        plt.plot(s.index, s.values, label=s.name)
    plt.legend()
    plt.title("Equity Curves")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200)
    plt.close()

def plot_metric_bars(summary_df: pd.DataFrame, metric: str, outpath: Path) -> None:
    plt.figure()
    x = summary_df["run"].astype(str).tolist()
    y = summary_df[metric].astype(float).tolist()
    plt.bar(x, y)
    plt.title(metric)
    plt.xticks(rotation=45, ha="right")
    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200)
    plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, help="comma-separated list of run directories")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    run_dirs = [Path(r.strip()) for r in args.runs.split(",") if r.strip()]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    summary_df = make_summary_table(run_dirs)
    summary_df.to_csv(outdir / "summary_table.csv", index=False, encoding="utf-8-sig")
    (outdir / "summary_table.md").write_text(summary_df.to_markdown(index=False), encoding="utf-8")

    equities = [read_equity(d) for d in run_dirs]
    plot_equity_curves(equities, outdir / "figures" / "equity_curves.png")

    for metric in ["CAGR","MDD","Calmar","Turnover_annual"]:
        if metric in summary_df.columns:
            plot_metric_bars(summary_df, metric, outdir / "figures" / f"{metric}.png")

    print(f"Saved report to {outdir}")

if __name__ == "__main__":
    main()
