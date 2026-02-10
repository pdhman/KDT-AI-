"""
실시간 레짐 판단 시스템 (KOSPI200 현물 지수 기준) - API 중심 버전
================================================================
핵심 로직:
1. 한투 API로 최근 1일 KOSPI200 현물 지수 조회
2. API 실패 시에만 CSV 백업 사용
3. VIX는 yfinance로 조회

출력:
- 콘솔 결과
- regime_result.json
- regime_result.csv
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import json
import os
import requests
import yaml
import time
warnings.filterwarnings('ignore')

# ================================================================
# 설정
# ================================================================

CONFIG = {
    'ma_threshold': 0.93,
    'ma_warning': 0.96,
    'vix_threshold': 22,
    'min_bear_days': 60,
    'min_bull_days': 100,
    'start_date': '2010-01-01',
    'config_path': 'config.yaml'
}

# ================================================================
# 한투 지수 API
# ================================================================

class KISIndexAPI:
    """한국투자증권 지수 API (심플 버전)"""

    def __init__(self, config_path='config.yaml'):
        """API 초기화"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        hantu = config['hantu']
        self.api_key = hantu['api_key']
        self.secret_key = hantu['secret_key']
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        self.token_cache_file = 'token_cache.json'

        self._get_token()

    def _load_cached_token(self):
        """캐시된 토큰 로드"""
        if not os.path.exists(self.token_cache_file):
            return None

        try:
            with open(self.token_cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # 만료 시간 확인 (5분 여유)
            expire_time = datetime.fromisoformat(cache['expire_time'])
            if datetime.now() < expire_time - timedelta(minutes=5):
                return cache['access_token']
        except:
            pass

        return None

    def _save_token_cache(self, token, expire_time):
        """토큰 캐시 저장"""
        cache = {
            'access_token': token,
            'expire_time': expire_time.isoformat(),
            'created_at': datetime.now().isoformat()
        }
        with open(self.token_cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    def _get_token(self):
        """토큰 발급 (캐시 우선)"""
        # 캐시된 토큰 확인
        cached_token = self._load_cached_token()
        if cached_token:
            self.access_token = cached_token
            return

        # 새로 발급
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.secret_key
        }
        res = requests.post(url, headers={"content-type": "application/json"}, json=body)
        result = res.json()

        if 'access_token' not in result:
            raise Exception(f"토큰 발급 실패: {result.get('error_description', 'Unknown error')}")

        self.access_token = result['access_token']

        # 만료 시간 계산 (24시간 - API 응답 기준)
        expire_time = datetime.now() + timedelta(seconds=result.get('expires_in', 86400))

        # 캐시 저장
        self._save_token_cache(self.access_token, expire_time)

    @staticmethod
    def get_kospi200_index_code():
        """
        KOSPI200 현물 지수 코드
        """
        return "0002"

    def get_latest_price(self, days_back=10):
        """
        최근 N일 KOSPI200 현물 지수 조회 후 가장 최근 1일 반환

        Args:
            days_back: 몇 일 전부터 조회할지 (영업일 확보용)

        Returns:
            dict: {'date': datetime, 'price': float} 또는 None
        """
        index_code = self.get_kospi200_index_code()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.api_key,
            "appsecret": self.secret_key,
            "tr_id": "FHKUP03500100"
        }

        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": index_code,
            "FID_INPUT_DATE_1": start_date.strftime('%Y%m%d'),
            "FID_INPUT_DATE_2": end_date.strftime('%Y%m%d'),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"
        }

        res = requests.get(url, headers=headers, params=params)

        if res.status_code != 200:
            raise Exception(f"API 호출 실패: {res.text}")

        data = res.json()

        if data.get('rt_cd') != '0':
            raise Exception(f"API 오류: {data.get('msg1')}")

        output = data.get('output2', [])

        if not output:
            return None

        # 가장 최근 데이터 (첫 번째)
        latest = output[0]

        return {
            'date': datetime.strptime(latest['stck_bsop_date'], '%Y%m%d'),
            'price': float(latest['bstp_nmix_prpr'])
        }

# ================================================================
# CSV 백업
# ================================================================

def load_csv_backup():
    """CSV 백업 데이터 로드 (API 실패 시)"""
    csv_path = 'Macro_data/kospi200_fut_daynight_long_20260131.csv'

    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])

    # 야간+주간 합산
    df_daily = df.groupby('date').agg({'정산가': 'last'}).reset_index()
    df_daily.columns = ['date', 'close']

    # 0원 제거
    df_daily = df_daily[df_daily['close'] > 0]

    df_daily['date'] = df_daily['date'].dt.date

    return df_daily

# ================================================================
# VIX 조회
# ================================================================

def get_latest_vix():
    """최근 VIX 조회"""
    import yfinance as yf

    vix = yf.download("^VIX", period="5d", progress=False)

    if len(vix) == 0:
        raise ValueError("VIX 데이터 없음")

    latest = vix.iloc[-1]

    # Series인 경우 첫 번째 값 추출
    close_value = latest['Close']
    if hasattr(close_value, 'values'):
        close_value = close_value.values[0]

    return {
        'date': latest.name.date(),
        'value': float(close_value)
    }

# ================================================================
# RegimeClassifier (기존과 동일)
# ================================================================

class RegimeClassifier:
    """레짐 분류기"""
    def __init__(self, config):
        self.ma_threshold = config['ma_threshold']
        self.ma_warning = config['ma_warning']
        self.vix_threshold = config['vix_threshold']
        self.min_bear_days = config['min_bear_days']
        self.min_bull_days = config['min_bull_days']

    def calculate_indicators(self, df):
        """지표 계산"""
        df = df.copy()

        for period in [5, 10, 20, 60, 200]:
            df[f'MA{period}'] = df['kospi200'].rolling(period, min_periods=1).mean()
            df[f'MA_ratio_{period}'] = df['kospi200'] / df[f'MA{period}']

        for period in [5, 10, 20, 60]:
            df[f'momentum_{period}'] = df['kospi200'].pct_change(period) * 100

        df['volatility_20'] = df['kospi200'].pct_change().rolling(20).std() * 100 * np.sqrt(252)

        return df

    def apply_rules(self, df):
        """룰 적용"""
        df = df.copy()

        rule1 = df['MA_ratio_200'] < self.ma_threshold
        rule2 = (df['MA_ratio_200'] < self.ma_warning) & (df['VIX'] > self.vix_threshold)

        df['raw_regime'] = (rule1 | rule2).astype(int)
        df['rule1_triggered'] = rule1.astype(int)
        df['rule2_triggered'] = rule2.astype(int)

        return df

    def apply_hysteresis(self, df):
        """히스테리시스"""
        df = df.copy()

        regime = df['raw_regime'].copy()
        current = 0
        start_idx = 0

        for i in range(len(regime)):
            if current == 0:
                if regime.iloc[i] == 1:
                    current = 1
                    start_idx = i
            else:
                days = i - start_idx
                if regime.iloc[i] == 0 and days >= self.min_bear_days:
                    current = 0
                    start_idx = i

            regime.iloc[i] = current

        df['regime'] = regime
        return df

    def predict(self, df):
        """전체 파이프라인"""
        df = self.calculate_indicators(df)
        df = self.apply_rules(df)
        df = self.apply_hysteresis(df)
        return df

# ================================================================
# 메인 로직
# ================================================================

def main():
    """메인 함수 - 심플 버전"""

    print("=" * 60)
    print("레짐 판단 시스템 (API 중심)")
    print("=" * 60)

    # 1. API로 최근 KOSPI200 지수 조회
    print("\n[1/3] KOSPI200 지수 조회 (API)...")

    try:
        api = KISIndexAPI(CONFIG['config_path'])
        latest_index = api.get_latest_price(days_back=10)

        if latest_index:
            idx_date = latest_index['date']
            idx_price = latest_index['price']
            print(f"  [OK] {idx_date.strftime('%Y-%m-%d')}: {idx_price:.2f}")
            data_source = "API"
        else:
            raise Exception("API 데이터 없음")

    except Exception as e:
        print(f"  [X] API 실패: {e}")
        print("  → CSV 백업 사용")

        csv_data = load_csv_backup()
        if csv_data is None:
            print("\n ERROR: CSV 백업도 없음")
            return None

        latest_row = csv_data.iloc[-1]
        idx_date = pd.to_datetime(latest_row['date'])
        idx_price = float(latest_row['close'])
        print(f"  [OK] CSV: {idx_date.strftime('%Y-%m-%d')}: {idx_price:.2f}")
        data_source = "CSV"

    # 2. VIX 조회
    print("\n[2/3] VIX 조회...")

    try:
        vix_data = get_latest_vix()
        vix_value = vix_data['value']
        print(f"  [OK] VIX: {vix_value:.2f}")
    except Exception as e:
        print(f"  [X] VIX 조회 실패: {e}")
        return None

    # 3. 과거 데이터 로드 (지표 계산용)
    print("\n[3/3] 과거 데이터 로드 (지표 계산)...")

    csv_data = load_csv_backup()
    if csv_data is None:
        print("  [X] CSV 없음")
        return None

    # 최신 데이터 추가/업데이트
    idx_date_obj = idx_date.date() if isinstance(idx_date, datetime) else idx_date

    # CSV에 최신 데이터가 있는지 확인
    if idx_date_obj in csv_data['date'].values:
        # 업데이트
        csv_data.loc[csv_data['date'] == idx_date_obj, 'close'] = idx_price
    else:
        # 추가
        new_row = pd.DataFrame({'date': [idx_date_obj], 'close': [idx_price]})
        csv_data = pd.concat([csv_data, new_row], ignore_index=True)
        csv_data = csv_data.sort_values('date').reset_index(drop=True)

    print(f"  [OK] 전체 {len(csv_data)}일 ({csv_data['date'].min()} ~ {csv_data['date'].max()})")

    # 4. VIX 데이터 준비
    vix_df = pd.DataFrame({
        'date': [vix_data['date']],
        'VIX': [vix_value]
    })

    # 5. 병합
    csv_data.columns = ['date', 'kospi200']
    df = pd.merge(csv_data, vix_df, on='date', how='left')

    # VIX 원본 날짜 기록 (결측치 추적용)
    df['VIX_original_date'] = df.apply(
        lambda row: row['date'] if pd.notna(row['VIX']) else None,
        axis=1
    )

    # VIX 결측치 처리: forward fill 후 backward fill
    df['VIX'] = df['VIX'].ffill().bfill()

    # forward fill로 채워진 경우 원본 날짜 전파
    last_original_date = None
    for i in range(len(df)):
        if df.loc[i, 'VIX_original_date'] is not None:
            last_original_date = df.loc[i, 'VIX_original_date']
        elif last_original_date is not None:
            df.loc[i, 'VIX_original_date'] = last_original_date

    # 여전히 결측치가 있으면 최신 VIX 값으로 채우기
    if df['VIX'].isna().any():
        df['VIX'] = df['VIX'].fillna(vix_value)
        # 최신 VIX로 채운 경우 날짜 기록
        df.loc[df['VIX_original_date'].isna(), 'VIX_original_date'] = vix_data['date']

    # 시작일 필터링
    start_dt = datetime.strptime(CONFIG['start_date'], '%Y-%m-%d').date()
    df = df[df['date'] >= start_dt].reset_index(drop=True)

    # 6. 레짐 분류
    print("\n레짐 분석 중...")
    classifier = RegimeClassifier(CONFIG)
    result = classifier.predict(df)

    # 7. 결과 추출
    latest = result.iloc[-1]

    current_date = str(latest['date'])
    current_price = float(latest['kospi200'])
    current_vix = float(latest['VIX'])
    current_vix_date = latest['VIX_original_date']
    current_regime = int(latest['regime'])

    ma_ratio_200 = float(latest['MA_ratio_200'])
    mom_20 = float(latest['momentum_20'])
    vol_20 = float(latest['volatility_20'])

    rule1 = bool(latest['rule1_triggered'])
    rule2 = bool(latest['rule2_triggered'])

    regime_name = "RISK_OFF" if current_regime == 1 else "RISK_ON"

    # 레짐 지속기간
    regime_series = result['regime'].values
    duration = 1
    for i in range(len(regime_series) - 2, -1, -1):
        if regime_series[i] == current_regime:
            duration += 1
        else:
            break

    # 8. 출력
    print("\n" + "=" * 60)
    print("분석 결과")
    print("=" * 60)

    print(f"\n기준 날짜: {current_date} ({data_source})")
    print(f"KOSPI200: {current_price:.2f}")

    # VIX 표시 (결측치 채운 경우 원본 날짜 표시)
    if str(current_vix_date) != current_date:
        print(f"VIX: {current_vix:.2f} (from {current_vix_date})")
    else:
        print(f"VIX: {current_vix:.2f}")
    print(f"MA200 비율: {ma_ratio_200:.4f}")
    print(f"20일 모멘텀: {mom_20:+.2f}%")

    print(f"\n최종 판단: {regime_name}")
    print(f"레짐 지속: {duration}일")

    if current_regime == 1:
        print("매매 권장: 전액 청산 (현금100%)")
    else:
        print("매매 권장: 정상 매매")

    # 경고
    alerts = []
    if current_vix > 30:
        alerts.append("⚠️ VIX 매우 높음 (30+)")
    if ma_ratio_200 < 0.93:
        alerts.append("⚠️ MA200 대비 -7% 하락")
    if rule1:
        alerts.append("🚨 규칙1 발동: BEAR 진입")

    if alerts:
        print()
        for alert in alerts:
            print(alert)

    # 9. 파일 저장
    result_json = {
        'timestamp': datetime.now().isoformat(),
        'date': current_date,
        'data_source': data_source,
        'regime': regime_name,
        'regime_duration_days': duration,
        'market': {
            'kospi200_index': round(current_price, 2),
            'vix': round(current_vix, 2),
            'vix_date': str(current_vix_date)
        },
        'indicators': {
            'ma_ratio_200': round(ma_ratio_200, 4),
            'momentum_20': round(mom_20, 2),
            'volatility_20': round(vol_20, 2)
        },
        'rules': {
            'rule1_triggered': rule1,
            'rule2_triggered': rule2
        },
        'alerts': alerts
    }

    with open('regime_result.json', 'w', encoding='utf-8') as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    summary_df = pd.DataFrame([{
        'date': current_date,
        'regime': regime_name,
        'duration': duration,
        'price': current_price,
        'vix': current_vix,
        'vix_date': str(current_vix_date),
        'ma_ratio_200': ma_ratio_200
    }])
    summary_df.to_csv('regime_result.csv', index=False)

    print("\n결과 저장: regime_result.json, regime_result.csv")
    print("=" * 60)

    return result_json

# ================================================================
# 실행
# ================================================================

if __name__ == "__main__":
    result = main()

    if result:
        print("\n[OK] 실행 완료")
    else:
        print("\n[FAIL] 실행 실패")
