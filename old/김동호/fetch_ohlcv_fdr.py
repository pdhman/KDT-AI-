"""
FinanceDataReader를 사용한 OHLCV 데이터 수집 스크립트

사전 준비:
pip install finance-datareader pandas tqdm

실행:
python fetch_ohlcv_fdr.py

장점:
- API 키 불필요
- 간단한 코드
- 빠른 수집
"""

import pandas as pd
import FinanceDataReader as fdr
from tqdm import tqdm
import time

# 종목 리스트 로드
print("종목 리스트 로딩...")
df_tickers = pd.read_csv('ticker_list.csv', dtype=str)
if 'clean_ticker' not in df_tickers.columns:
    df_tickers['clean_ticker'] = df_tickers['ticker'].str.replace('^A', '', regex=True)
df_tickers['clean_ticker'] = df_tickers['clean_ticker'].str.zfill(6)
print(f"총 {len(df_tickers)} 종목")

# 날짜 설정
start_date = "2023-01-02"
end_date = "2025-12-30"

# OHLCV 데이터 수집
all_data = []
failed_tickers = []

print(f"\nOHLCV 데이터 수집 시작 ({start_date} ~ {end_date})...")
for idx, row in tqdm(df_tickers.iterrows(), total=len(df_tickers), desc="종목 수집"):
    ticker = row['ticker']
    name = row['name']
    clean_ticker = str(row['clean_ticker']).zfill(6)
    
    try:
        # FDR로 데이터 조회
        df_stock = fdr.DataReader(clean_ticker, start_date, end_date)
        
        if df_stock.empty:
            failed_tickers.append((ticker, name))
            print(f"  ⚠️  {ticker} ({name}): 데이터 없음")
            continue
        
        # 인덱스를 컬럼으로 변환
        df_stock = df_stock.reset_index()
        
        # 컬럼명 확인 및 변경
        # FDR 기본 컬럼: Date, Open, High, Low, Close, Volume, Change
        df_stock.columns = ['date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Change']
        
        # Adj Close 추가 (FDR의 Close는 이미 수정주가)
        df_stock['Adj Close'] = df_stock['Close']
        
        # ticker, name 추가
        df_stock['ticker'] = ticker
        df_stock['name'] = name
        
        # 필요한 컬럼만 선택
        df_stock = df_stock[['date', 'ticker', 'name', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
        
        all_data.append(df_stock)
        
        # 진행상황 출력 (10개마다)
        if (idx + 1) % 10 == 0:
            print(f"  진행: {idx + 1}/{len(df_tickers)} 종목 완료")
        
        # API 부하 방지
        time.sleep(0.05)
        
    except Exception as e:
        failed_tickers.append((ticker, name))
        print(f"  ❌ {ticker} ({name}) 실패: {e}")
        continue

# 최종 데이터프레임 생성
if all_data:
    df_ohlcv = pd.concat(all_data, ignore_index=True)
    df_ohlcv['date'] = pd.to_datetime(df_ohlcv['date'])
    
    print("\n" + "="*60)
    print("수집 완료!")
    print("="*60)
    print(f"✅ 성공: {len(all_data)} 종목")
    print(f"❌ 실패: {len(failed_tickers)} 종목")
    
    if failed_tickers:
        print("\n실패한 종목 (처음 20개):")
        for ticker, name in failed_tickers[:20]:
            print(f"  - {ticker}: {name}")
        if len(failed_tickers) > 20:
            print(f"  ... 외 {len(failed_tickers) - 20}개")
    
    print(f"\n📊 총 데이터: {len(df_ohlcv):,} rows")
    print(f"📅 날짜 범위: {df_ohlcv['date'].min().date()} ~ {df_ohlcv['date'].max().date()}")
    print(f"🏢 종목 수: {df_ohlcv['ticker'].nunique()}")
    
    # 기본 통계
    print("\n📈 가격 통계:")
    print(df_ohlcv[['Open', 'High', 'Low', 'Close', 'Volume']].describe())
    
    # 샘플 확인
    print("\n샘플 데이터 (삼성전자):")
    samsung = df_ohlcv[df_ohlcv['ticker'] == 'A005930'].head(5)
    print(samsung)
    
    # 결측치 확인
    print("\n결측치 확인:")
    print(df_ohlcv.isnull().sum())
    
    # 저장
    output_path = 'ohlcv_data.csv'
    df_ohlcv.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n✅ 저장 완료: {output_path}")
    print(f"파일 크기: {len(df_ohlcv):,} rows × {len(df_ohlcv.columns)} columns")
    
else:
    print("\n❌ 수집된 데이터가 없습니다.")

print("\n완료! 이제 이 파일을 Claude에 업로드하세요.")
