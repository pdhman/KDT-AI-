"""
KOSPI 보통주 OHLCV 데이터 수집기 v2
=====================================
- 기간: 2016-01-01 ~ 2026-01-01
- 대상: KOSPI 보통주 (우선주/스팩/리츠/ETF 제외)
- 필터: 상폐 종목 제외, 중간 상장 종목 표시
- 스크리닝: 연평균 거래대금 상위 250위에 1년이라도 진입 → safe
- 출력: 통합 CSV (date,ticker,open,high,low,close,volume)
- 데이터 소스: pykrx (KRX 스크래핑)

사용법:
    pip install pykrx pandas
    python "fetch_kospi_ohlcv (2).py"
"""

import os
import re
import time
import warnings
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

warnings.filterwarnings("ignore")

# ============================================================
# 설정
# ============================================================
START_DATE = "20160101"
END_DATE = "20260101"
MARKET = "KOSPI"
OUTPUT_DIR = "./kospi_ohlcv_data"
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "krx_ohlcv_20160101_20260101.csv")
TOP_N = 250                  # 연평균 거래대금 상위 N위 기준
SLEEP_SEC = 1.0              # KRX 차단 방지


# ============================================================
# 1) 유틸리티
# ============================================================
def is_common_stock(ticker: str) -> bool:
    """보통주 여부 (끝자리 0이면 보통주)"""
    return ticker[-1] == "0"


def is_spac_or_special(name: str) -> bool:
    """스팩/리츠/기타 특수 종목"""
    patterns = [r"스팩", r"제\d+호", r"리츠$", r"기업인수목적", r"SPAC"]
    return any(re.search(pat, name) for pat in patterns)


def get_nearest_business_day(date_str: str, direction="backward") -> str:
    """가장 가까운 영업일 찾기"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    for _ in range(10):
        tickers = stock.get_market_ticker_list(dt.strftime("%Y%m%d"), market=MARKET)
        if len(tickers) > 0:
            return dt.strftime("%Y%m%d")
        dt += timedelta(days=1) if direction == "forward" else timedelta(days=-1)
    return date_str


def get_trading_days(biz_start: str, biz_end: str) -> list:
    """기간 내 거래일 목록 (삼성전자 OHLCV 인덱스 활용)"""
    print("  거래일 목록 조회 중 ...")
    df = stock.get_market_ohlcv(biz_start, biz_end, "005930")
    time.sleep(SLEEP_SEC)
    days = [d.strftime("%Y%m%d") for d in df.index]
    print(f"  총 {len(days)}개 거래일 확인")
    return days


# ============================================================
# 2) 종목 유니버스 (보통주, 상폐 제외, 중간상장 표시)
# ============================================================
def build_universe():
    print("=" * 60)
    print("[STEP 1] 종목 유니버스 구성")
    print("=" * 60)

    biz_start = get_nearest_business_day(START_DATE, direction="forward")
    biz_end = get_nearest_business_day(END_DATE, direction="backward")
    print(f"  시작 영업일: {biz_start}")
    print(f"  종료 영업일: {biz_end}")

    tickers_start = set(stock.get_market_ticker_list(biz_start, market=MARKET))
    tickers_end = set(stock.get_market_ticker_list(biz_end, market=MARKET))

    universe = {}
    for ticker in sorted(tickers_end):
        name = stock.get_market_ticker_name(ticker)
        if not is_common_stock(ticker):
            continue
        if is_spac_or_special(name):
            continue
        universe[ticker] = {
            "ticker": ticker,
            "name": name,
            "mid_listed": ticker not in tickers_start,
        }

    mid_count = sum(1 for v in universe.values() if v["mid_listed"])
    print(f"  종료일 KOSPI 전체: {len(tickers_end)}개")
    print(f"  보통주 필터 후:    {len(universe)}개")
    print(f"  그 중 중간 상장:   {mid_count}개")

    return universe, biz_start, biz_end


# ============================================================
# 3) 거래대금 스크리닝 — 연평균 기준 Top250
#    연도별(2016~2025)로 전종목 평균 거래대금을 구한 뒤,
#    어느 한 해라도 상위 250위 안에 들면 safe
# ============================================================
def screen_by_trading_value(universe: dict, biz_start: str, biz_end: str):
    print()
    print("=" * 60)
    print("[STEP 2] 연평균 거래대금 상위 250위 스크리닝")
    print("=" * 60)

    years = list(range(
        int(biz_start[:4]),
        int(biz_end[:4]) + 1,
    ))
    print(f"  대상 연도: {years[0]}~{years[-1]} ({len(years)}년)")

    safe_tickers = set()
    universe_tickers = set(universe.keys())
    yearly_results = {}  # {year: {ticker: avg_trading_value}}

    for year in years:
        y_start = f"{year}0101"
        y_end = f"{year}1231"
        # 기간 경계 보정
        if y_start < biz_start:
            y_start = biz_start
        if y_end > biz_end:
            y_end = biz_end

        print(f"\n  [{year}] {y_start}~{y_end} 전종목 시세 수집 중 ...", end=" ", flush=True)

        try:
            # 연도 내 매 월초 스냅샷을 모아 해당 연도 평균 거래대금 추정
            # (전 거래일을 조회하면 너무 오래 걸리므로, 월초 샘플링)
            monthly_frames = []
            for month in range(1, 13):
                sample_date = f"{year}{month:02d}01"
                if sample_date < y_start or sample_date > y_end:
                    continue
                # 해당 월의 영업일 찾기
                sample_biz = get_nearest_business_day(sample_date, direction="forward")
                if sample_biz[:4] != str(year):
                    continue  # 연도 넘어가면 스킵

                try:
                    df_day = stock.get_market_ohlcv(sample_biz, market=MARKET)
                    time.sleep(SLEEP_SEC)
                    if not df_day.empty:
                        if "거래대금" not in df_day.columns:
                            df_day["거래대금"] = df_day["종가"] * df_day["거래량"]
                        monthly_frames.append(df_day[["거래대금"]])
                except Exception:
                    pass

            if not monthly_frames:
                print("데이터 없음")
                continue

            # 월별 스냅샷을 concat → 종목별 평균 거래대금
            df_concat = pd.concat(monthly_frames)
            avg_by_ticker = df_concat.groupby(df_concat.index)["거래대금"].mean()

            # 유니버스 종목만 필터
            avg_by_ticker = avg_by_ticker[avg_by_ticker.index.isin(universe_tickers)]

            # 상위 250위
            if len(avg_by_ticker) <= TOP_N:
                top_n_tickers = set(avg_by_ticker.index.tolist())
            else:
                top_n_tickers = set(avg_by_ticker.nlargest(TOP_N).index.tolist())

            safe_tickers.update(top_n_tickers)
            yearly_results[year] = avg_by_ticker.to_dict()

            print(f"종목 {len(avg_by_ticker)}개 중 Top{TOP_N} 선정, 누적 safe={len(safe_tickers)}")

        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\n  스크리닝 완료: 유니버스 {len(universe)}개 → safe {len(safe_tickers)}개")

    # 연도별 순위 정보 저장 (디버깅용)
    try:
        rows = []
        for year, data in yearly_results.items():
            sorted_items = sorted(data.items(), key=lambda x: -x[1])
            for rank, (ticker, val) in enumerate(sorted_items, 1):
                if ticker in universe:
                    rows.append({
                        "year": year, "rank": rank, "ticker": ticker,
                        "name": universe[ticker]["name"],
                        "avg_trading_value": int(val),
                        "is_top250": rank <= TOP_N,
                    })
        df_rank = pd.DataFrame(rows)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df_rank.to_csv(os.path.join(OUTPUT_DIR, "_debug_yearly_ranks.csv"), index=False, encoding="utf-8-sig")
        print(f"  연도별 순위 저장: _debug_yearly_ranks.csv")
    except Exception:
        pass

    return safe_tickers


# ============================================================
# 4) OHLCV 수집 (safe 종목만)
# ============================================================
def fetch_ohlcv(universe: dict, safe_tickers: set, biz_start: str, biz_end: str):
    print()
    print("=" * 60)
    print("[STEP 3] OHLCV 데이터 수집 (safe 종목)")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    safe_list = [universe[t] for t in sorted(safe_tickers) if t in universe]
    total = len(safe_list)
    passed, failed = [], []
    all_frames = []  # 통합 CSV용

    for i, item in enumerate(safe_list):
        ticker = item["ticker"]
        name = item["name"]
        mid_listed = item["mid_listed"]

        print(f"  [{i+1:4d}/{total}] {ticker} {name}", end=" ... ")

        try:
            df = stock.get_market_ohlcv(biz_start, biz_end, ticker)
            time.sleep(SLEEP_SEC)

            if df.empty:
                print("데이터 없음 → SKIP")
                continue

            df = df.rename(columns={
                "시가": "open", "고가": "high", "저가": "low",
                "종가": "close", "거래량": "volume",
                "거래대금": "trading_value", "등락률": "change_rate",
            })

            # 통합 CSV용 DataFrame 구성: date,ticker,open,high,low,close,volume
            df_out = df[["open", "high", "low", "close", "volume"]].copy()
            df_out.index.name = "date"
            df_out["ticker"] = ticker
            all_frames.append(df_out)

            d_start = str(df_out.index[0].date()) if hasattr(df_out.index[0], "date") else str(df_out.index[0])
            d_end = str(df_out.index[-1].date()) if hasattr(df_out.index[-1], "date") else str(df_out.index[-1])

            passed.append({
                "ticker": ticker, "name": name, "mid_listed": mid_listed,
                "data_start": d_start, "data_end": d_end, "num_rows": len(df_out),
            })
            marker = " ★신규상장" if mid_listed else ""
            print(f"OK ({len(df_out)}일){marker}")

        except Exception as e:
            print(f"ERROR: {e}")
            failed.append({"ticker": ticker, "name": name, "error": str(e)})
            time.sleep(SLEEP_SEC)

    return passed, failed, all_frames


# ============================================================
# 5) 메타 저장
# ============================================================
def save_combined_csv(all_frames):
    """통합 CSV 저장: date,ticker,open,high,low,close,volume"""
    print()
    print("=" * 60)
    print("[STEP 4] 통합 CSV 저장")
    print("=" * 60)

    if not all_frames:
        print("  저장할 데이터 없음")
        return

    df_all = pd.concat(all_frames)
    df_all = df_all.reset_index()

    # date 포맷 통일
    df_all["date"] = pd.to_datetime(df_all["date"]).dt.strftime("%Y-%m-%d")

    # 컬럼 순서: date,ticker,open,high,low,close,volume
    df_all = df_all[["date", "ticker", "open", "high", "low", "close", "volume"]]
    df_all = df_all.sort_values(["date", "ticker"]).reset_index(drop=True)

    df_all.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(f"  파일: {OUTPUT_CSV}")
    print(f"  총 {len(df_all):,}행, {df_all['ticker'].nunique()}종목")
    print(f"  기간: {df_all['date'].min()} ~ {df_all['date'].max()}")


def save_meta(passed, failed):
    print()
    print("=" * 60)
    print("[STEP 5] 메타 정보 저장")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df_meta = pd.DataFrame(passed)
    df_meta.to_csv(os.path.join(OUTPUT_DIR, "_meta_universe.csv"), index=False, encoding="utf-8-sig")
    print(f"  전체 메타:     _meta_universe.csv ({len(df_meta)}개)")

    df_mid = df_meta[df_meta["mid_listed"] == True]
    if not df_mid.empty:
        df_mid.to_csv(os.path.join(OUTPUT_DIR, "_meta_mid_listed.csv"), index=False, encoding="utf-8-sig")
        print(f"  중간상장 메타: _meta_mid_listed.csv ({len(df_mid)}개)")

    if failed:
        pd.DataFrame(failed).to_csv(os.path.join(OUTPUT_DIR, "_meta_failed.csv"), index=False, encoding="utf-8-sig")
        print(f"  실패 종목:     _meta_failed.csv ({len(failed)}개)")

    print()
    print("-" * 60)
    all_count = len(passed)
    full_count = sum(1 for t in passed if not t["mid_listed"])
    mid_count = sum(1 for t in passed if t["mid_listed"])
    print(f"  safe 종목 (OHLCV 저장): {all_count}개")
    print(f"    전체 기간 상장:       {full_count}개")
    print(f"    중간 상장 (★):        {mid_count}개")
    print(f"    수집 실패:            {len(failed)}개")
    print(f"  저장 경로: {os.path.abspath(OUTPUT_DIR)}/")
    print("-" * 60)


# ============================================================
# 6) 메인
# ============================================================
def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  KOSPI 보통주 OHLCV 수집기 v2                               ║")
    print("║  2016-01-01 ~ 2026-01-01                                    ║")
    print("║  보통주 / 상폐제외 / 연평균 거래대금 Top250 1회이상 = safe ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    t0 = time.time()

    universe, biz_start, biz_end = build_universe()
    safe_tickers = screen_by_trading_value(universe, biz_start, biz_end)
    passed, failed, all_frames = fetch_ohlcv(universe, safe_tickers, biz_start, biz_end)
    save_combined_csv(all_frames)
    save_meta(passed, failed)

    print(f"\n  총 소요: {(time.time()-t0)/60:.1f}분")
    print("  완료!")


if __name__ == "__main__":
    main()
