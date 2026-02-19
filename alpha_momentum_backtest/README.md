# Alpha Momentum Backtest

> KRX 조정주가(분할/병합 반영)를 사용한 모멘텀 기반 백테스트 프로젝트
> 분석 기간: **2013-12-01 ~ 2025-12-31**

---

## 프로젝트 개요

한국 주식시장(KRX)을 대상으로 한 모멘텀 전략 백테스트입니다.

- KRX **조정주가(adjusted close)** 기반으로 데이터 정확성을 확보
- 혼합 모멘텀(6-1, 12-1)을 유연하게 조합
- 월별/주별 리밸런싱 비교 가능
- 거래비용, 슬리피지, 보유 제약, 레짐 대응을 **옵션화**
- 성과 분석 결과를 **PPT용 표/그래프**까지 자동 생성

v3에서는 특히 **일별 mark-to-market equity 기록**을 적용하여,
월별·연도별 MDD(기간 내 최대 낙폭)를 **정확하게 계산**할 수 있습니다.

---

## 주요 기능 (Features)

### 1. 데이터
- KRX **조정 종가(adjusted close)** 사용
  - 액면분할 / 병합 / 권리락 반영
- 데이터 수집: `pykrx`

### 2. 모멘텀 전략
- **Mixed Momentum**
  - 6-1 모멘텀
  - 12-1 모멘텀
- 가중치 `w`로 비율 조절
  - `w = 0.0` → 12-1 모멘텀만 사용
  - `w = 0.5` → 6-1 / 12-1 동일 비중
  - `w = 1.0` → 6-1 모멘텀만 사용

### 3. 리밸런싱
- 월별(monthly)
- 주별(weekly)

### 4. 거래비용
- 수수료 (편도)
  - 예: 0.15% → `0.0015`
- 슬리피지
  - 추가 비용(편도)
  - 예: 0.05% → `0.0005`
- **총 편도 비용 = 수수료 + 슬리피지**

### 5. 제약 조건 (Constraints)
- `min_hold_months`
  - 최소 보유기간 제약 (매도 제한)
- `reentry_ban_months`
  - 재진입 금지기간 (진짜 의미의 쿨다운)

### 6. 레짐 대응 (선택 옵션)
- 코스피200 **200일 이동평균(MA200)** 기반
- 조건:
  - 시장 종가 < 200MA → Risk-Off
- Risk-Off 시:
  - 포트폴리오 익스포저를 `risk_off_exposure`로 축소 (기본 0.5)

---

## 폴더 구조 및 파일 설명

alpha_momentum_backtest/
├─ alpha_bt/                 # 백테스트 핵심 라이브러리
│  ├─ backtest.py            # 백테스트 실행 로직 (v3: 일별 MTM equity 기록)
│  ├─ dataio.py              # 데이터 로딩/저장 유틸리티
│  ├─ krx_fetch.py           # KRX 데이터 수집 로직
│  ├─ calendar_utils.py      # 거래일, 리밸런싱 날짜 유틸
│  ├─ indicators/            # 팩터/지표 모듈
│  │  └─ momentum.py         # 6-1, 12-1 및 mixed momentum 계산
│  ├─ engine/                # 포트폴리오/매매 엔진
│  │  ├─ portfolio.py        # 포지션, 현금, 거래 기록 관리
│  │  └─ execution.py        # 리밸런싱 및 거래비용/슬리피지 처리
│  └─ reports/               # 성과 분석 및 리포트 산출
│     ├─ metrics.py          # CAGR, MDD, Sharpe 등 성과 지표 계산
│     ├─ periodic.py         # 월별/연도별 수익률 및 MDD 계산
│     └─ export.py           # CSV/JSON 결과 저장
│
├─ scripts/                  # 실행 스크립트 모음
│  ├─ fetch_prices.py        # 유니버스 기반 종목 가격 수집
│  ├─ run_single.py          # 단일 전략 백테스트 실행
│  ├─ grid_search.py         # 파라미터 그리드 서치 실행
│  ├─ make_benchmark_plots.py# 전략 vs KOSPI200 Equity/MDD 그래프 생성
│  └─ make_report.py         # PPT/리포트용 표·그래프 자동 생성
│
├─ data/                     # 입력 데이터
│  ├─ universe_top100.csv    # 시총 상위 100 종목 유니버스 티커 예시
│  ├─ universe_top200.csv    # 시총 상위 200 종목 유니버스 티커 예시
│  ├─ prices_*.parquet       # 유니버스별 종목 가격 데이터
│  └─ kospi200_index_close.parquet # 코스피200 가격지수 (벤치마크/레짐)
│
├─ outputs/                  # 백테스트 결과
│  ├─ single/                # 단일 전략 실행 결과
│  ├─ grid/                  # 그리드 서치 결과
│  └─ benchmark/             # 벤치마크 비교 그래프 및 테이블
│
├─ requirements.txt          # Python 의존성 목록
└─ README.md                 # 프로젝트 설명 문서

---
## 출력 결과 (Outputs)

### 단일 실행 (Single Run)
`outputs/single/...`

- `summary.json` : 성과 요약 (CAGR, MDD, Sharpe 등)
- `equity.csv` : 일별 equity curve (daily mark-to-market)
- `returns.csv` : 일별 수익률
- `traded_notional.csv` : 거래대금
- `monthly_returns.csv`
- `monthly_mdd.csv`
- `yearly_returns.csv`
- `yearly_mdd.csv`

### Grid Search
`outputs/grid/...`

- 파라미터 조합별 성과 요약 테이블

### PPT / 리포트용 산출물
`outputs/report/...`

- 비교 테이블
- Equity / Drawdown 그래프
- PPT에 바로 사용 가능한 이미지

---

## 설치 (Install)

```bash
pip install -r requirements.txt
```

---

## 유니버스 (Universes)

사용자가 준비한 예시:

- `data/universe_top100.csv`
- `data/universe_top200.csv`

형식:

```csv
ticker,name(optional)
```

---

## 가격 데이터 수집

### 종목 가격 (유니버스별)

```bash
python -m scripts.fetch_prices --start 20131202 --end 20251231 \
  --universe data/universe_top100.csv --out data/prices_top100.parquet

python -m scripts.fetch_prices --start 20131202 --end 20251231 \
  --universe data/universe_top200.csv --out data/prices_top200.parquet
```

### 시장 지수 (코스피200)

레짐 대응 및 벤치마크 비교용:

```bash
python -m scripts.fetch_market_index --start 20131202 --end 20251231 \
  --out data/kospi200_index_close.parquet
```

---

## 단일 백테스트 실행 예시

### 월별 리밸런싱 + 최소 보유기간

```bash
python -m scripts.run_single \
  --prices data/prices_top200.parquet \
  --start 20131202 --end 20251231 \
  --N 10 --w 0.2 --rebalance monthly \
  --fee 0.0015 --slip 0.0000 \
  --min_hold 4 --reentry_ban 0 \
  --regime ma200 --market data/kospi200_index_close.parquet \
  --risk_off_exposure 0.5 \
  --outdir outputs/single/top200_monthly_holdonly
```

### 주별 리밸런싱 비교

```bash
python -m scripts.run_single \
  --prices data/prices_top200.parquet \
  --start 20131202 --end 20251231 \
  --N 10 --w 0.2 --rebalance weekly \
  --fee 0.0015 --slip 0.0005 \
  --min_hold 4 --reentry_ban 0 --regime none \
  --outdir outputs/single/top200_weekly_holdonly
```

---

## 리포트 생성

```bash
python -m scripts.make_report \
  --runs outputs/single/top200_monthly_holdonly,outputs/single/top200_weekly_holdonly \
  --outdir outputs/report
```

## Equity & Drawdown 그래프 생성

```bash
python -m scripts.make_benchmark_plots \
  --prices data/prices_top200.parquet \
  --market data/kospi200_index_close.parquet \
  --start 20131202 --end 20251231 \
  --N 10 --w 0.2 --rebalance monthly \
  --fee 0.0015 --slip 0.0005 \
  --min_hold 4 --reentry_ban 0 --regime none --outdir outputs/benchmark/u200_hold_4_n_10
```
---

## 참고

- 전략 성과는 **정규화된 equity 기준**으로 비교하는 것을 권장
- 벤치마크는 전략 유니버스와 정합성을 맞추기 위해 **코스피200 가격지수** 사용
