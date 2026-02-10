# Market Regime Classification System

실시간 시장 레짐(regime) 분류를 통한 체계적 투자 비중 조절 시스템

## 개요 (Overview)

본 시스템은 KOSPI200 지수와 VIX(변동성 지수)를 활용하여 시장 상태를 실시간으로 분석하고, RISK_ON(강세장) 또는 RISK_OFF(약세장) 레짐을 판단합니다. 룰 베이스 분류 방법론과 히스테리시스(hysteresis) 메커니즘을 결합하여 안정적이고 신뢰성 있는 시장 레짐 판단을 제공합니다.

### 주요 특징 (Key Features)

- **목적**: 계량적 지표 기반 시장 레짐 분류 및 투자 비중 권고
- **방법론**: 룰 베이스 분류기 + 히스테리시스 메커니즘
- **출력**: 간결한 콘솔 출력 + JSON/CSV 상세 결과
- **성능**: 94.7% Recall, 전환 빈도 3.2회/년 (안정적)


### 기본 실행

```bash
python live_regime_check_minimal_v2.py
```

### 출력 예시

```
데이터 다운로드 중...
완료

VIX: 16.34 (보통)
MA200 비율: 1.5784 (매우 높음 (강세))
20일 모멘텀: +8.52% (상승)

최종 판단: RISK_ON
매매 권장: 정상 매매
현재 레짐 지속: 245일

결과 저장: regime_result.json, regime_result.csv

실행 완료
```

### 출력 파일

실행 결과로 다음 파일이 생성됩니다:
- `regime_result.json` - 전체 분석 결과 (JSON 형식)
- `regime_result.csv` - 요약 결과 (CSV 형식)

## 데이터 출처 (Data Sources)

| Asset | Provider | Description |
|-------|----------|-------------|
| VIX | yfinance | CBOE Volatility Index (변동성 지수) |
| KOSPI200 | FinanceDataReader | Korea Composite Stock Price Index 200 |

데이터는 2010년 1월 1일부터 현재까지 일별 종가 기준으로 수집됩니다.

## 방법론 (Methodology)

### 레짐 분류 규칙 (Regime Classification Rules)

시스템은 다음 두 가지 규칙 중 하나라도 충족될 경우 RISK_OFF(BEAR) 레짐으로 분류합니다:

**규칙 1 (Rule 1): MA200 강한 하락**
```python
MA_ratio_200 < 0.93
```
현재가가 200일 이동평균선 대비 7% 이상 하락한 경우

**규칙 2 (Rule 2): MA200 하락 + VIX 상승 (복합 신호)**
```python
(MA_ratio_200 < 0.96) AND (VIX > 22)
```
가격 하락과 높은 변동성이 동시에 관찰되는 경우

### 히스테리시스 메커니즘 (Hysteresis Mechanism)

레짐 전환의 안정성을 확보하기 위해 히스테리시스를 적용합니다:

- **BEAR 진입**: 조건 충족 시 즉시 전환
- **BULL 복귀**: 최소 **60거래일** BEAR 레짐 유지 후 전환 가능
- **효과**: 단기 노이즈로 인한 빈번한 레짐 전환 방지 (연평균 3.2회)

### 기술적 지표 (Technical Indicators)

#### 1. 이동평균 비율 (Moving Average Ratio)
```python
MA_ratio_n = Price_current / MA_n
```
여기서 n ∈ {5, 10, 20, 60, 200}

**해석**:
- MA_ratio > 1.0: 상승 추세
- MA_ratio < 1.0: 하락 추세

**출력 사용**: MA_ratio_200 (장기 추세 확인)

#### 2. 모멘텀 (Momentum)
```python
momentum_n = ((Price_t / Price_(t-n)) - 1) × 100
```
여기서 n ∈ {5, 10, 20, 60}

**해석**:
- `> +10%`: 강한 상승
- `+3% ~ +10%`: 상승
- `-3% ~ +3%`: 보합
- `-10% ~ -3%`: 하락
- `< -10%`: 강한 하락

**출력 사용**: momentum_20 (단기 방향성 확인)

#### 3. 실현 변동성 (Realized Volatility)
```python
volatility_20 = std(returns_daily, 20) × √252 × 100
```

**해석**:
- `< 15%`: 낮음 (안정)
- `15-25%`: 보통
- `25-35%`: 높음 (주의)
- `> 35%`: 매우 높음 (위험)

**참고**: VIX와 상관관계 있으나, KOSPI200 기준 실현 변동성

#### 4. VIX (CBOE Volatility Index)
```
외부 데이터 (yfinance)
```

**해석**:
- `< 15`: 낮음 (안정)
- `15-22`: 보통
- `22-30`: 높음 (주의)
- `> 30`: 매우 높음 (위험)

**출력 사용**: 글로벌 위험 수준 확인

## 콘솔 출력 정보 (Console Output)

### 기본 정보 (항상 표시)

1. **VIX**: 변동성 지수 (위험 수준)
2. **MA200 비율**: 장기 추세 (200일 이동평균 대비)
3. **20일 모멘텀**: 단기 방향성 (상승/하락 중)
4. **최종 판단**: RISK_ON / RISK_OFF
5. **매매 권장**: 정상 매매 / 전액 청산
6. **현재 레짐 지속**: 현재 레짐이 며칠째 유지 중인지

### 조건부 경고 (위험 신호 발생 시만)

- ⚠️ VIX 극심한 공포 (40+) - 플래시 크래시 위험
- ⚠️ VIX 매우 높음 (30+) - 고위험 구간
- ⚠️ MA200 대비 -10% 이상 급락
- ⚠️ MA200 대비 -7% 하락 (BEAR 임계값)
- 🚨 규칙1 발동: MA200 < 0.93 (강한 BEAR)
- 🚨 규칙2 발동: MA200 < 0.96 AND VIX > 22

## 출력 형식 (Output Format)

### JSON 출력 (regime_result.json)

```json
{
  "timestamp": "2026-02-03T12:03:06.678459",
  "date": "2026-02-03",
  "regime": "RISK_ON",
  "regime_duration_days": 245,
  "market": {
    "kospi200": 761.08,
    "vix": 16.34
  },
  "indicators": {
    "ma_ratio_20": 1.0668,
    "ma_ratio_60": 1.2219,
    "ma_ratio_200": 1.5709,
    "momentum_5": 2.14,
    "momentum_20": 15.41,
    "momentum_60": 33.9,
    "volatility_20": 31.27
  },
  "rules": {
    "rule1_triggered": false,
    "rule2_triggered": false
  },
  "alerts": []
}
```

**RISK_OFF 시 추가 필드**:
```json
{
  "recommended_position": "현금 100%",
  "alerts": [
    "⚠️ VIX 극심한 공포 (40+) - 플래시 크래시 위험",
    "🚨 규칙1 발동: MA200 < 0.93 (강한 BEAR)"
  ]
}
```

### CSV 출력 (regime_result.csv)

| date | regime | duration_days | kospi200 | vix | ma_ratio_200 | momentum_20 | volatility_20 |
|------|--------|---------------|----------|-----|--------------|-------------|---------------|
| 2026-02-03 | RISK_ON | 245 | 761.08 | 16.34 | 1.5709 | 15.41 | 31.27 |

**RISK_OFF 시 추가 컬럼**: `recommended_position`

## 설정 (Configuration)

`live_regime_check_minimal_v2.py` 파일 내 CONFIG 딕셔너리에서 파라미터 조정 가능:

```python
CONFIG = {
    'ma_threshold': 0.93,      # Rule 1: MA200 임계값 (강한 BEAR)
    'ma_warning': 0.96,        # Rule 2: MA200 경고 임계값
    'vix_threshold': 22,       # Rule 2: VIX 임계값
    'min_bear_days': 60,       # BEAR 레짐 최소 유지 기간 (거래일)
    'min_bull_days': 100,      # BULL 레짐 최소 유지 기간 (미사용)
    'start_date': '2010-01-01' # 백테스트 시작일
}
```

### 파라미터 설명

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `ma_threshold` | 0.93 | 규칙1 임계값: MA200 대비 -7% 하락 |
| `ma_warning` | 0.96 | 규칙2 임계값: MA200 대비 -4% 하락 |
| `vix_threshold` | 22 | 규칙2 VIX 임계값: 22 초과 시 경고 |
| `min_bear_days` | 60 | BEAR → BULL 전환 최소 기간 (안정성) |
| `min_bull_days` | 100 | 미사용 (현재 구현에서 불필요) |

## 투자 가이드라인 (Investment Guidelines)

### RISK_ON (강세장, Bull Market)

**매매 권장**: 정상 매매

**투자 전략**:
- 적극적 매수 전략
- 성장주, 인덱스 추종
- 정상 비중 유지

**포지션 관리**:
- 분할 매수 전략
- 시장 추세 추종
- 손절선 설정 (느슨하게)

### RISK_OFF (약세장, Bear Market)

**매매 권장**: 전액 청산 (현금 100%)

**투자 전략**:
- 즉시 청산
- 현금 보유
- 시장 회복 대기

**포지션 관리**:
- 모든 포지션 청산
- 레버리지 제거
- 최소 60일 이상 BEAR 유지 시 BULL 복귀 가능

**참고**: BEAR 진입 후 평균 60일 이상 지속되므로, 조기 재진입 자제

## 시나리오별 판단 예시

### 1. 안정적 상승장 ✅
```
VIX: 15 (낮음) + MA200: 1.20 (높음) + 모멘텀: +8%
→ 위험 낮고, 장기 강세, 상승 중
→ 정상 매매
```

### 2. 급락 중 🚨
```
VIX: 30 (높음) + MA200: 0.90 (낮음) + 모멘텀: -15%
→ 위험 높고, 장기 약세, 급락 중
→ 전액 청산 (RISK_OFF 가능성 높음)
```

### 3. 조정 중 (반등 가능) ⚠️
```
VIX: 25 (높음) + MA200: 1.15 (높음) + 모멘텀: -5%
→ 일시적 조정, 장기는 강세
→ 정상 매매 (RISK_ON 유지)
```

### 4. 반등 시도 💡
```
VIX: 18 (보통) + MA200: 0.94 (낮음) + 모멘텀: +6%
→ 바닥 다지기 후 반등 시도
→ 주의 관찰 (규칙2 발동 가능)
```

### 5. 상승 피로 🤔
```
VIX: 12 (낮음) + MA200: 1.30 (매우 높음) + 모멘텀: +1%
→ 장기 강세지만 상승 둔화
→ 정상 매매 (과열 주의)
```

## 성능 지표 (Performance Metrics)

| 지표 | 값 | 설명 |
|------|-----|------|
| BEAR Recall | 93.0% | BEAR 구간 포착률 |
| 전체 Recall | 94.7% | 전체 위기 구간 포착률 |
| 평균 적중률 | 92.6% | 평균 레짐 분류 정확도 |
| 전환 빈도 | 3.2회/년 | 연평균 레짐 전환 횟수 (안정적) |
| COVID 적중률 | 78.3% | COVID-19 급락 구간 포착률 |

## 주의사항 (Important Notes)

### 히스테리시스 효과
- BEAR 진입 후 최소 60일 유지
- 단기 반등에도 BEAR 유지 (안정성)
- BULL 복귀는 신중하게 판단

### 레짐 지속 기간 활용
- 지속 기간 짧음 (< 20일): 불안정, 재전환 가능성
- 지속 기간 중간 (20-60일): 정상, 관찰 필요
- 지속 기간 긺 (> 60일): 매우 안정적

### 경고 신호 해석
- 규칙 발동 없이 레짐 유지: 히스테리시스 효과
- 경고 표시 시: 레짐 전환 가능성 높음
- VIX 40+ 경고: 즉각 대응 필요
