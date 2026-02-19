import argparse
from alpha_bt.dataio import read_universe_csv, save_prices_panel
from alpha_bt.krx_fetch import fetch_adjusted_close_panel

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--universe", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    uni = read_universe_csv(args.universe)
    tickers = uni["ticker"].tolist()
    prices = fetch_adjusted_close_panel(tickers, args.start, args.end)
    save_prices_panel(prices, args.out)
    print(f"Saved prices panel: {args.out} shape={prices.shape}")

if __name__ == "__main__":
    main()
