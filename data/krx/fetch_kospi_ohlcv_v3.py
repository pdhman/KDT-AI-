"""
KOSPI 보통주 OHLCV 데이터 수집기 v3
=====================================
v2 대비 개선점:
  ① sleep 보강      : 모든 pykrx 호출을 safe_call()로 감싸 sleep + 재시도(backoff) 적용
  ② 증분 저장/resume: 종목별로 CSV에 append 저장. 중간에 죽어도 이어받기 가능
  ③ 예외 로깅       : 조용히 삼키지 않고 logging 으로 파일 + 콘솔에 기록
  ④ 생존편향 제거   : 유니버스를 "연도별 종목 리스트의 합집합"으로 구성
                      → 기간 중 상장폐지된 종목도 포함(상폐 시점까지 데이터 수집)

- 기간: 2016-01-01 ~ 2026-01-01
- 대상: KOSPI 보통주 (우선주/스팩/리츠/ETF 제외)
- 스크리닝: 연평균 거래대금 상위 250위에 1년이라도 진입 → safe
- 출력: 통합 CSV (date,ticker,open,high,low,close,volume)
- 데이터 소스: pykrx (KRX 스크래핑)

사용법:
    pip install -U pykrx pandas
    python fetch_kospi_ohlcv_v3.py           # 처음부터
    python fetch_kospi_ohlcv_v3.py           # 다시 실행하면 자동 이어받기(resume)
    RESUME=0 python fetch_kospi_ohlcv_v3.py  # 처음부터 다시(기존 파일 무시)
"""

import os
import re
import sys
import time
import logging
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

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(_BASE_DIR, "kospi_ohlcv_data")
OUTPUT_CSV = os.path.join(_BASE_DIR, "krx_ohlcv_20160101_20260101.csv")

TOP_N = 250                     # 연평균 거래대금 상위 N위 기준

# ② 이어받기: 환경변수 RESUME=0 이면 처음부터 다시
RESUME = os.environ.get("RESUME", "1") != "0"

# ① sleep / 재시도 설정 (KRX 차단 방지)
OHLCV_SLEEP = 1.0               # OHLCV 등 무거운 호출 뒤 sleep
LIST_SLEEP = 0.5               # 종목리스트/종목명 등 가벼운 호출 뒤 sleep
MAX_RETRY = 3                   # 예외 발생 시 재시도 횟수
RETRY_BACKOFF = 2.0             # 재시도 대기 배수 (2s, 4s, 8s ...)

# 증분 저장용 메타 파일
META_PROGRESS = os.path.join(OUTPUT_DIR, "_meta_progress.csv")   # 종목별 진행/성공 기록
META_FAILED = os.path.join(OUTPUT_DIR, "_meta_failed.csv")       # 실패 기록
LOG_FILE = os.path.join(OUTPUT_DIR, "fetch.log")


# ============================================================
# ③ 로깅 설정
# ============================================================
def setup_logger():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger = logging.getLogger("kospi_fetch")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# ============================================================
# ① API 안전 호출 래퍼 (sleep + 재시도 + 로깅)
# ============================================================
def safe_call(fn, *args, sleep=OHLCV_SLEEP, retries=MAX_RETRY, label="", **kwargs):
    """
    pykrx 호출을 감싸서:
      - 성공 시 sleep 후 결과 반환
      - 예외 시 backoff 로 재시도, 최종 실패하면 로깅 후 None 반환
    주의: KRX 차단은 '예외'가 아니라 '빈 결과'로 오는 경우가 많으므로,
          호출부에서 empty 여부도 함께 확인/로깅한다.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            result = fn(*args, **kwargs)
            time.sleep(sleep)
            return result
        except Exception as e:  # noqa: BLE001 - 의도적으로 넓게 잡아 재시도
            last_err = e
            wait = sleep * (RETRY_BACKOFF ** attempt)
            logger.warning(f"{label} 실패 (시도 {attempt}/{retries}): {e} → {wait:.1f}s 후 재시도")
            time.sleep(wait)
    logger.error(f"{label} 최종 실패: {last_err}")
    return None


# ============================================================
# 유틸리티
# ============================================================
def is_common_stock(ticker: str) -> bool:
    """보통주 여부 (끝자리 0이면 보통주) — API 호출 없는 순수 문자열 판정"""
    return ticker[-1] == "0"


def is_spac_or_special(name: str) -> bool:
    """스팩/리츠/기타 특수 종목"""
    patterns = [r"스팩", r"제\d+호", r"리츠$", r"기업인수목적", r"SPAC"]
    return any(re.search(pat, name) for pat in patterns)


def get_ticker_list(date_str: str) -> list:
    lst = safe_call(stock.get_market_ticker_list, date_str, market=MARKET,
                    sleep=LIST_SLEEP, label=f"ticker_list({date_str})")
    return lst if lst else []


def get_ticker_name(ticker: str) -> str:
    name = safe_call(stock.get_market_ticker_name, ticker,
                     sleep=LIST_SLEEP, label=f"ticker_name({ticker})")
    return name if name else ticker  # 상폐 종목 등 실패 시 코드로 대체


def get_nearest_business_day(date_str: str, direction="backward") -> str:
    """가장 가까운 영업일 찾기 (각 조회에 sleep 적용)"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    for _ in range(10):
        tickers = get_ticker_list(dt.strftime("%Y%m%d"))
        if len(tickers) > 0:
            return dt.strftime("%Y%m%d")
        dt += timedelta(days=1) if direction == "forward" else timedelta(days=-1)
    logger.warning(f"영업일 탐색 실패: {date_str} 근처 10일 내 거래일 없음")
    return date_str


# ============================================================
# ④ 종목 유니버스 — 연도별 합집합 (생존편향 제거)
#    각 연도(및 시작/종료) 시점의 KOSPI 종목 리스트를 모두 합쳐서
#    기간 중 상장폐지된 종목까지 포함시킨다.
# ============================================================
def build_universe():
    logger.info("=" * 60)
    logger.info("[STEP 1] 종목 유니버스 구성 (연도별 합집합 = 생존편향 제거)")
    logger.info("=" * 60)

    biz_start = get_nearest_business_day(START_DATE, direction="forward")
    biz_end = get_nearest_business_day(END_DATE, direction="backward")
    logger.info(f"  시작 영업일: {biz_start}")
    logger.info(f"  종료 영업일: {biz_end}")

    # 연도별 스냅샷 날짜(각 연도 중반 6월 말 기준) + 시작/종료
    snapshot_dates = []
    for year in range(int(biz_start[:4]), int(biz_end[:4]) + 1):
        snapshot_dates.append(f"{year}0701")
    snapshot_dates += [biz_start, biz_end]

    union_tickers = set()
    for d in sorted(set(snapshot_dates)):
        if d < biz_start or d > biz_end:
            continue
        bd = get_nearest_business_day(d, direction="backward")
        lst = get_ticker_list(bd)
        logger.info(f"  스냅샷 {bd}: {len(lst)}종목 (누적 합집합 {len(union_tickers | set(lst))})")
        union_tickers |= set(lst)

    tickers_start = set(get_ticker_list(biz_start))
    tickers_end = set(get_ticker_list(biz_end))

    logger.info(f"  합집합 전체(전 종목): {len(union_tickers)}개 — 종목명 조회 시작(보통주만)")

    universe = {}
    checked = 0
    for ticker in sorted(union_tickers):
        # API 호출 없는 보통주 필터를 먼저 적용해 종목명 조회 횟수를 줄인다
        if not is_common_stock(ticker):
            continue
        name = get_ticker_name(ticker)
        checked += 1
        if is_spac_or_special(name):
            continue
        universe[ticker] = {
            "ticker": ticker,
            "name": name,
            "mid_listed": ticker not in tickers_start,   # 기간 중 상장
            "delisted": ticker not in tickers_end,        # 기간 중 상장폐지
        }

    mid_count = sum(1 for v in universe.values() if v["mid_listed"])
    del_count = sum(1 for v in universe.values() if v["delisted"])
    logger.info(f"  종목명 조회: {checked}건")
    logger.info(f"  보통주/특수종목 필터 후 유니버스: {len(universe)}개")
    logger.info(f"    그 중 중간 상장: {mid_count}개, 상장폐지: {del_count}개")

    return universe, biz_start, biz_end


# ============================================================
# 거래대금 스크리닝 — 연평균 기준 Top250
# ============================================================
def screen_by_trading_value(universe: dict, biz_start: str, biz_end: str):
    logger.info("")
    logger.info("=" * 60)
    logger.info("[STEP 2] 연평균 거래대금 상위 250위 스크리닝")
    logger.info("=" * 60)

    years = list(range(int(biz_start[:4]), int(biz_end[:4]) + 1))
    logger.info(f"  대상 연도: {years[0]}~{years[-1]} ({len(years)}년)")

    safe_tickers = set()
    universe_tickers = set(universe.keys())
    yearly_results = {}

    for year in years:
        y_start = max(f"{year}0101", biz_start)
        y_end = min(f"{year}1231", biz_end)

        logger.info(f"  [{year}] {y_start}~{y_end} 월초 스냅샷 수집 중 ...")

        monthly_frames = []
        for month in range(1, 13):
            sample_date = f"{year}{month:02d}01"
            if sample_date < y_start or sample_date > y_end:
                continue
            sample_biz = get_nearest_business_day(sample_date, direction="forward")
            if sample_biz[:4] != str(year):
                continue  # 연도 넘어가면 스킵

            df_day = safe_call(stock.get_market_ohlcv, sample_biz, market=MARKET,
                               sleep=OHLCV_SLEEP, label=f"snapshot({sample_biz})")
            if df_day is None:
                continue
            if df_day.empty:
                logger.debug(f"    {sample_biz} 스냅샷 비어있음(휴장/차단 가능)")
                continue
            if "거래대금" not in df_day.columns:
                df_day["거래대금"] = df_day["종가"] * df_day["거래량"]
            monthly_frames.append(df_day[["거래대금"]])

        if not monthly_frames:
            logger.warning(f"  [{year}] 데이터 없음 → 스킵")
            continue

        df_concat = pd.concat(monthly_frames)
        avg_by_ticker = df_concat.groupby(df_concat.index)["거래대금"].mean()
        avg_by_ticker = avg_by_ticker[avg_by_ticker.index.isin(universe_tickers)]

        if len(avg_by_ticker) <= TOP_N:
            top_n_tickers = set(avg_by_ticker.index.tolist())
        else:
            top_n_tickers = set(avg_by_ticker.nlargest(TOP_N).index.tolist())

        safe_tickers.update(top_n_tickers)
        yearly_results[year] = avg_by_ticker.to_dict()
        logger.info(f"  [{year}] 종목 {len(avg_by_ticker)}개 중 Top{TOP_N} 선정, 누적 safe={len(safe_tickers)}")

    logger.info(f"  스크리닝 완료: 유니버스 {len(universe)}개 → safe {len(safe_tickers)}개")

    # 연도별 순위 저장 (디버깅용)
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
        if rows:
            pd.DataFrame(rows).to_csv(
                os.path.join(OUTPUT_DIR, "_debug_yearly_ranks.csv"),
                index=False, encoding="utf-8-sig")
            logger.info("  연도별 순위 저장: _debug_yearly_ranks.csv")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"  연도별 순위 저장 실패: {e}")

    return safe_tickers


# ============================================================
# ② 증분 저장 유틸
# ============================================================
def load_done_tickers() -> set:
    """이미 성공적으로 저장된 종목(status==OK) 목록 — resume 용."""
    if RESUME and os.path.exists(META_PROGRESS):
        try:
            df = pd.read_csv(META_PROGRESS, dtype={"ticker": str})
            done = set(df.loc[df["status"] == "OK", "ticker"].unique())
            logger.info(f"  이어받기(resume): 이미 저장된 {len(done)}종목은 스킵")
            return done
        except Exception as e:  # noqa: BLE001
            logger.warning(f"  기존 진행파일 읽기 실패, 처음부터 진행: {e}")
    return set()


def append_csv(path: str, df: pd.DataFrame):
    """헤더 유무를 파악해 CSV에 append."""
    header = (not os.path.exists(path)) or os.path.getsize(path) == 0
    df.to_csv(path, mode="a", header=header, index=False, encoding="utf-8-sig")


def fresh_start_cleanup():
    """RESUME=0 일 때 기존 산출물 초기화."""
    if RESUME:
        return
    for p in (OUTPUT_CSV, META_PROGRESS, META_FAILED):
        if os.path.exists(p):
            os.remove(p)
            logger.info(f"  RESUME=0 → 기존 파일 삭제: {os.path.basename(p)}")


# ============================================================
# OHLCV 수집 (safe 종목만) — 종목별 즉시 저장
# ============================================================
def fetch_ohlcv(universe: dict, safe_tickers: set, biz_start: str, biz_end: str):
    logger.info("")
    logger.info("=" * 60)
    logger.info("[STEP 3] OHLCV 데이터 수집 (safe 종목, 종목별 증분 저장)")
    logger.info("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fresh_start_cleanup()
    done = load_done_tickers()

    safe_list = [universe[t] for t in sorted(safe_tickers) if t in universe]
    total = len(safe_list)
    ok_count = fail_count = skip_count = 0

    for i, item in enumerate(safe_list):
        ticker = item["ticker"]
        name = item["name"]

        if ticker in done:
            skip_count += 1
            continue

        prefix = f"  [{i + 1:4d}/{total}] {ticker} {name}"

        df = safe_call(stock.get_market_ohlcv, biz_start, biz_end, ticker,
                       sleep=OHLCV_SLEEP, label=f"ohlcv({ticker})")

        if df is None:
            logger.error(f"{prefix} ... 수집 실패(재시도 소진)")
            append_csv(META_FAILED, pd.DataFrame([{
                "ticker": ticker, "name": name, "error": "retry_exhausted",
                "ts": datetime.now().isoformat(timespec="seconds"),
            }]))
            fail_count += 1
            continue

        if df.empty:
            logger.warning(f"{prefix} ... 데이터 없음 → SKIP")
            append_csv(META_PROGRESS, pd.DataFrame([{
                "ticker": ticker, "name": name,
                "mid_listed": item["mid_listed"], "delisted": item["delisted"],
                "data_start": "", "data_end": "", "num_rows": 0, "status": "EMPTY",
            }]))
            continue

        df = df.rename(columns={
            "시가": "open", "고가": "high", "저가": "low",
            "종가": "close", "거래량": "volume",
        })
        df_out = df[["open", "high", "low", "close", "volume"]].copy()
        df_out.index.name = "date"
        df_out = df_out.reset_index()
        df_out["date"] = pd.to_datetime(df_out["date"]).dt.strftime("%Y-%m-%d")
        df_out["ticker"] = ticker
        df_out = df_out[["date", "ticker", "open", "high", "low", "close", "volume"]]

        # 1) OHLCV 먼저 append → 2) 진행 메타 append (순서 중요: 크래시 시 재수집 가능)
        append_csv(OUTPUT_CSV, df_out)
        append_csv(META_PROGRESS, pd.DataFrame([{
            "ticker": ticker, "name": name,
            "mid_listed": item["mid_listed"], "delisted": item["delisted"],
            "data_start": df_out["date"].iloc[0], "data_end": df_out["date"].iloc[-1],
            "num_rows": len(df_out), "status": "OK",
        }]))

        marker = ""
        if item["delisted"]:
            marker = " ☠상폐"
        elif item["mid_listed"]:
            marker = " ★신규상장"
        logger.info(f"{prefix} ... OK ({len(df_out)}일){marker}")
        ok_count += 1

    logger.info("")
    logger.info("-" * 60)
    logger.info(f"  성공 저장: {ok_count}개 / 스킵(이미완료): {skip_count}개 / 실패: {fail_count}개")
    logger.info("-" * 60)
    return ok_count, fail_count, skip_count


# ============================================================
# 최종 정렬/중복제거
# ============================================================
def finalize_csv():
    logger.info("")
    logger.info("=" * 60)
    logger.info("[STEP 4] 통합 CSV 정렬/중복제거")
    logger.info("=" * 60)

    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        logger.warning("  저장된 데이터 없음")
        return

    try:
        df = pd.read_csv(OUTPUT_CSV, dtype={"ticker": str})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        before = len(df)
        df = (df.drop_duplicates(subset=["date", "ticker"])
                .sort_values(["date", "ticker"])
                .reset_index(drop=True))
        df = df[["date", "ticker", "open", "high", "low", "close", "volume"]]
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

        logger.info(f"  파일: {OUTPUT_CSV}")
        logger.info(f"  {before:,}행 → 중복제거 후 {len(df):,}행, {df['ticker'].nunique()}종목")
        logger.info(f"  기간: {df['date'].min()} ~ {df['date'].max()}")
    except Exception as e:  # noqa: BLE001
        # 정렬 실패해도 append 된 원본 데이터는 그대로 보존됨
        logger.error(f"  최종 정렬 실패(데이터는 CSV에 보존됨): {e}")


# ============================================================
# 메인
# ============================================================
def main():
    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║  KOSPI 보통주 OHLCV 수집기 v3 (2016-01-01 ~ 2026-01-01)  ║")
    logger.info("║  연도별 합집합 유니버스 / 증분저장·resume / 로깅          ║")
    logger.info("╚══════════════════════════════════════════════════════════╝")
    logger.info(f"  RESUME = {RESUME} (환경변수 RESUME=0 이면 처음부터)")

    t0 = time.time()
    try:
        universe, biz_start, biz_end = build_universe()
        safe_tickers = screen_by_trading_value(universe, biz_start, biz_end)
        fetch_ohlcv(universe, safe_tickers, biz_start, biz_end)
        finalize_csv()
    except KeyboardInterrupt:
        logger.warning("사용자 중단(Ctrl+C). 지금까지 저장된 데이터는 보존됩니다. "
                       "다시 실행하면 이어받기됩니다.")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"예기치 못한 오류로 중단: {e}. "
                         f"저장된 데이터는 보존되며 재실행 시 이어받기됩니다.")

    logger.info(f"  총 소요: {(time.time() - t0) / 60:.1f}분 / 로그: {LOG_FILE}")
    logger.info("  종료")


if __name__ == "__main__":
    main()
