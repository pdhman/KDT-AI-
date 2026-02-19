import argparse
from pathlib import Path
from alpha_bt.krx_fetch import build_universe_by_mcap

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYYMMDD (trading day)")
    ap.add_argument("--market", default="KOSPI", choices=["KOSPI","KOSDAQ"])
    ap.add_argument("--mcap_min", type=int, default=500_000_000_000)
    ap.add_argument("--out", default="data/universe.csv")
    args = ap.parse_args()

    df = build_universe_by_mcap(args.date, args.market, args.mcap_min)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[["ticker","name"]].to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Saved universe: {out} (n={len(df)})")

if __name__ == "__main__":
    main()
