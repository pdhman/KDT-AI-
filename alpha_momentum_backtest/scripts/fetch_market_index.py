import argparse
from pathlib import Path
from alpha_bt.krx_fetch import fetch_kospi200_index_close

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    s = fetch_kospi200_index_close(args.start, args.end)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.to_frame("close").to_parquet(out, index=True)
    print(f"Saved KOSPI200 index close: {out} n={len(s)}")

if __name__ == "__main__":
    main()
