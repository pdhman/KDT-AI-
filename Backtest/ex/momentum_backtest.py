r"""
모멘텀 전략 백테스트 시스템 (신용비율 유니버스 필터 적용)

유니버스 필터:
- 3개월(60거래일) 이동평균 신용비율 >= 0.15 → 매수 가능 유니버스
- 3개월(60거래일) 이동평균 신용비율 <  0.15 → 매도 후보 (보유 시 강제 매도)

매수 조건 (유니버스 내 AND 조건):
1. 신용비율 3개월 MA >= 0.15 (유니버스 필터 통과)
2. CCI > 100 상향 돌파
3. MACD 골든크로스
4. 볼린저 밴드 중심선 상향 돌파

매도 조건 (OR 조건 - 하나라도 만족하면 매도):
1. 신용비율 3개월 MA < 0.15 (유니버스 이탈)
2. CCI < -100: 과매도 진입 (모멘텀 약화)
3. MACD 데드크로스: MACD선이 시그널선 아래로 하향 돌파
4. 볼린저 밴드 중심선 이탈: 가격이 20일 이평선 아래로 하락
5. (비활성화) 손절매: 진입가 대비 -5% 하락 시
6. (비활성화) 익절매: 진입가 대비 +15% 상승 시

데이터:
- OHLCV: C:\Users\jeeho\Desktop\pj3\project3\ohlcv_data.csv
- 신용비율: C:\Users\jeeho\Desktop\pj3\project3\김동호\unified_data.csv
"""

# 필요한 라이브러리 임포트
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 120


class MomentumStrategy:
    """모멘텀 지표 계산 클래스"""
    
    def calculate_cci(self, df: pd.DataFrame, period=20) -> pd.Series:
        """CCI (Commodity Channel Index) 계산"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - sma) / (0.015 * mad)
        return cci
    
    def calculate_macd(self, df: pd.DataFrame, 
                       fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD 계산"""
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line
        return macd, signal_line, histogram
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, 
                                  period=20, std=2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """볼린저 밴드 계산"""
        middle = df['close'].rolling(window=period).mean()
        std_dev = df['close'].rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        return upper, middle, lower


class BacktestEngine:
    """모멘텀 전략 백테스트 엔진"""
    
    def __init__(self, initial_capital=10000000, commission=0.00015):
        """
        initial_capital: 초기 자본 (기본 1000만원)
        commission: 거래 수수료율 (기본 0.015%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.strategy = MomentumStrategy()
        
    def run_backtest(self, ticker: str, df: pd.DataFrame,
                     position_size=0.3, credit_ratio_threshold=0.15,
                     cci_period=20, macd_fast=12, macd_slow=26, macd_signal=9) -> Dict:
        """
        단일 종목 백테스트
        position_size: 포지션 비율 (기본 30%)
        credit_ratio_threshold: 신용비율 3개월 MA 유니버스 편입 기준 (기본 0.15)
        cci_period: CCI 계산 기간 (기본 20)
        macd_fast/slow/signal: MACD 파라미터 (기본 12, 26, 9)
        """
        # 지표 계산
        df['cci'] = self.strategy.calculate_cci(df, period=cci_period)
        df['macd'], df['signal'], df['histogram'] = self.strategy.calculate_macd(
            df, fast=macd_fast, slow=macd_slow, signal=macd_signal)
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self.strategy.calculate_bollinger_bands(df)

        # 신용비율 3개월(60거래일) 이동평균 계산
        # shift(1): T+1 공시 반영 → 전일까지의 MA로 당일 판단
        has_credit_ratio = 'credit_ratio' in df.columns
        if has_credit_ratio:
            df['credit_ratio_ma60'] = df['credit_ratio'].rolling(window=60).mean().shift(1)

        # 거래 기록
        trades = []
        position = None  # 현재 포지션
        cash = self.initial_capital

        # 60일 MA + shift(1) 확보를 위해 시작 인덱스 조정
        start_idx = 61 if has_credit_ratio else 50

        # 시그널 당일 감지 → 익일 시가 집행이므로 마지막 날은 시그널만 (집행 불가)
        for i in range(start_idx, len(df) - 1):
            current = df.iloc[i]
            previous = df.iloc[i-1]
            next_day = df.iloc[i+1]  # 익일 시가로 집행

            # 유니버스 필터: 신용비율 3개월 MA >= threshold → 매수 가능
            if has_credit_ratio:
                in_buy_universe = (pd.notna(current['credit_ratio_ma60']) and
                                   current['credit_ratio_ma60'] >= credit_ratio_threshold)
            else:
                in_buy_universe = True

            # 매수 신호: 유니버스 내에서만 매수 가능
            if position is None:
                if not in_buy_universe:
                    continue  # 유니버스 밖이면 매수 불가

                cci_breakout = current['cci'] > 100 and previous['cci'] <= 100
                macd_golden = (current['macd'] > current['signal'] and
                              previous['macd'] <= previous['signal'])
                price_above_bb = (current['close'] > current['bb_middle'] and
                                 previous['close'] <= previous['bb_middle'])

                if cci_breakout and macd_golden and price_above_bb:
                    # 익일 시가로 매수 집행
                    buy_price = next_day['open']
                    buy_amount = cash * position_size
                    shares = int(buy_amount / buy_price)
                    buy_cost = shares * buy_price * (1 + self.commission)

                    if shares > 0 and buy_cost <= cash:
                        position = {
                            'entry_date': next_day['date'],
                            'entry_price': buy_price,
                            'shares': shares,
                            'entry_cci': current['cci'],
                            'entry_macd': current['macd']
                        }
                        cash -= buy_cost

            # 매도 신호
            elif position is not None:
                # 유니버스 이탈 매도: 신용비율 3개월 MA가 기준 미달
                universe_exit = has_credit_ratio and not in_buy_universe

                # 기존 매도 조건
                cci_exit = current['cci'] < -100
                macd_dead = (current['macd'] < current['signal'] and
                            previous['macd'] >= previous['signal'])
                price_below_bb = current['close'] < current['bb_middle']

                # 손절/익절 (비활성화)
                # returns = (current['close'] - position['entry_price']) / position['entry_price']
                # stop_loss = returns < -0.05  # -5% 손절
                # take_profit = returns > 0.15  # +15% 익절

                if universe_exit or cci_exit or macd_dead or price_below_bb:
                    # 익일 시가로 매도 집행
                    sell_price = next_day['open']
                    sell_amount = position['shares'] * sell_price * (1 - self.commission)

                    trade_return = (sell_price - position['entry_price']) / position['entry_price']

                    trades.append({
                        'ticker': ticker,
                        'entry_date': position['entry_date'],
                        'exit_date': next_day['date'],
                        'entry_price': position['entry_price'],
                        'exit_price': sell_price,
                        'shares': position['shares'],
                        'return': trade_return,
                        'profit': sell_amount - (position['shares'] * position['entry_price']),
                        'exit_reason': 'universe_exit' if universe_exit else
                                      'cci_exit' if cci_exit else
                                      'macd_dead' if macd_dead else
                                      'price_below_bb',
                        'holding_days': (next_day['date'] - position['entry_date']).days
                    })

                    cash += sell_amount
                    position = None
        
        # 미청산 포지션 처리
        if position is not None:
            final_price = df.iloc[-1]['close']
            sell_amount = position['shares'] * final_price * (1 - self.commission)
            trade_return = (final_price - position['entry_price']) / position['entry_price']
            
            trades.append({
                'ticker': ticker,
                'entry_date': position['entry_date'],
                'exit_date': df.iloc[-1]['date'],
                'entry_price': position['entry_price'],
                'exit_price': final_price,
                'shares': position['shares'],
                'return': trade_return,
                'profit': sell_amount - (position['shares'] * position['entry_price']),
                'exit_reason': 'end_of_period',
                'holding_days': (df.iloc[-1]['date'] - position['entry_date']).days
            })
            cash += sell_amount
        
        return {
            'trades': trades,
            'final_capital': cash,
            'total_return': (cash - self.initial_capital) / self.initial_capital
        }
    
    def calculate_metrics(self, all_trades: List[Dict]) -> Dict:
        """백테스트 성과 지표 계산"""
        if not all_trades:
            return {}
        
        df_trades = pd.DataFrame(all_trades)
        
        total_trades = len(df_trades)
        winning_trades = len(df_trades[df_trades['return'] > 0])
        losing_trades = len(df_trades[df_trades['return'] < 0])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        avg_win = df_trades[df_trades['return'] > 0]['return'].mean() if winning_trades > 0 else 0
        avg_loss = df_trades[df_trades['return'] < 0]['return'].mean() if losing_trades > 0 else 0
        
        profit_factor = abs(avg_win * winning_trades / (avg_loss * losing_trades)) if losing_trades > 0 else float('inf')
        
        total_profit = df_trades['profit'].sum()
        avg_return = df_trades['return'].mean()
        max_return = df_trades['return'].max()
        min_return = df_trades['return'].min()
        
        avg_holding_days = df_trades['holding_days'].mean()
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_profit': total_profit,
            'avg_return': avg_return,
            'max_return': max_return,
            'min_return': min_return,
            'avg_holding_days': avg_holding_days
        }


class LocalCSVBacktester:
    """로컬 CSV 파일을 사용한 백테스터 (신용비율 유니버스 필터 적용)"""

    def __init__(self, csv_path: str, unified_csv_path: str = None):
        """
        csv_path: OHLCV 데이터 CSV 경로
        unified_csv_path: unified_data CSV 경로 (신용비율 포함)
        """
        self.csv_path = csv_path
        self.unified_csv_path = unified_csv_path
        self.backtest_engine = BacktestEngine()
        self.full_data = None
        self.unified_data = None
        self.stock_list = {}

    def load_data(self):
        """CSV 파일 전체 로드 및 종목 목록 추출"""
        print(f"Loading OHLCV data from {self.csv_path}...")
        self.full_data = pd.read_csv(self.csv_path)

        # 컬럼명 변환 (Open -> open 등)
        self.full_data.columns = ['date', 'ticker', 'name', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        self.full_data['date'] = pd.to_datetime(self.full_data['date'])

        # unified_data 로드 (신용비율)
        if self.unified_csv_path and os.path.exists(self.unified_csv_path):
            print(f"Loading unified data from {self.unified_csv_path}...")
            self.unified_data = pd.read_csv(self.unified_csv_path)
            self.unified_data['date'] = pd.to_datetime(self.unified_data['date'])
            print(f"  Unified data: {len(self.unified_data)} rows, "
                  f"{self.unified_data['ticker'].nunique()} stocks")
        else:
            print("WARNING: unified_data not found. Running without credit ratio filter.")

        # 종목 목록 추출
        stocks = self.full_data[['ticker', 'name']].drop_duplicates()
        self.stock_list = dict(zip(stocks['ticker'], stocks['name']))

        print(f"Loaded {len(self.full_data)} rows, {len(self.stock_list)} stocks")
        print(f"Date range: {self.full_data['date'].min()} ~ {self.full_data['date'].max()}")

        return self.stock_list

    def get_historical_data(self, ticker: str) -> pd.DataFrame:
        """특정 종목의 OHLCV + 신용비율 데이터 추출"""
        try:
            if self.full_data is None:
                self.load_data()

            df = self.full_data[self.full_data['ticker'] == ticker].copy()
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].sort_values('date').reset_index(drop=True)

            # 신용비율 데이터 병합
            if self.unified_data is not None:
                credit = self.unified_data[self.unified_data['ticker'] == ticker][['date', 'credit_ratio']].copy()
                if len(credit) > 0:
                    df = df.merge(credit, on='date', how='left')

            return df

        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()
    
    def run_portfolio_backtest(self, cci_period=20, macd_fast=12,
                               macd_slow=26, macd_signal=9) -> Dict:
        """포트폴리오 백테스트"""
        # 데이터 로드
        if self.full_data is None:
            self.load_data()
        
        all_results = []
        all_trades = []
        
        print("=" * 80)
        print(f"백테스트 기간: {self.full_data['date'].min().strftime('%Y-%m-%d')} ~ {self.full_data['date'].max().strftime('%Y-%m-%d')}")
        print(f"대상 종목: {len(self.stock_list)}개")
        print("=" * 80)
        
        for ticker, name in self.stock_list.items():
            try:
                print(f"\n[{ticker}] {name} 백테스트 중...")
                
                # 데이터 조회
                df = self.get_historical_data(ticker)
                
                if len(df) < 50:
                    print(f"  ⚠️  데이터 부족 ({len(df)}일)")
                    continue
                
                # 백테스트 실행
                result = self.backtest_engine.run_backtest(
                    ticker, df, cci_period=cci_period,
                    macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal)
                
                result['ticker'] = ticker
                result['name'] = name
                all_results.append(result)
                all_trades.extend(result['trades'])
                
                print(f"  ✅ 완료 - 거래횟수: {len(result['trades'])}, "
                      f"수익률: {result['total_return']*100:.2f}%")
                
            except Exception as e:
                print(f"  ❌ 에러: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 전체 성과 분석
        metrics = self.backtest_engine.calculate_metrics(all_trades)
        
        return {
            'individual_results': all_results,
            'all_trades': all_trades,
            'metrics': metrics
        }
    
    def print_results(self, backtest_result: Dict):
        """백테스트 결과 출력"""
        metrics = backtest_result['metrics']
        
        print("\n" + "=" * 80)
        print("백테스트 결과 요약")
        print("=" * 80)
        
        print(f"\n📊 전체 통계")
        print(f"  총 거래 횟수: {metrics['total_trades']}회")
        print(f"  승리 거래: {metrics['winning_trades']}회")
        print(f"  패배 거래: {metrics['losing_trades']}회")
        print(f"  승률: {metrics['win_rate']*100:.2f}%")
        
        print(f"\n💰 수익성")
        print(f"  평균 수익률: {metrics['avg_return']*100:.2f}%")
        print(f"  평균 승리: {metrics['avg_win']*100:.2f}%")
        print(f"  평균 손실: {metrics['avg_loss']*100:.2f}%")
        print(f"  손익비: {metrics['profit_factor']:.2f}")
        print(f"  총 수익: {metrics['total_profit']:,.0f}원")
        
        print(f"\n📈 극값")
        print(f"  최대 수익: {metrics['max_return']*100:.2f}%")
        print(f"  최대 손실: {metrics['min_return']*100:.2f}%")
        
        print(f"\n⏱️  보유 기간")
        print(f"  평균 보유일: {metrics['avg_holding_days']:.1f}일")
        
        # 종목별 성과
        print(f"\n📋 종목별 성과 (상위 10개)")
        print("-" * 80)
        
        individual = backtest_result['individual_results']
        individual_sorted = sorted(individual, key=lambda x: x['total_return'], reverse=True)
        
        for i, result in enumerate(individual_sorted[:10], 1):
            print(f"{i:2d}. [{result['ticker']}] {result['name']:15s} "
                  f"거래:{len(result['trades']):2d}회  "
                  f"수익률:{result['total_return']*100:7.2f}%")
        
        # 거래 상세 (최근 10건)
        print(f"\n📝 최근 거래 내역 (최근 10건)")
        print("-" * 80)
        
        trades_df = pd.DataFrame(backtest_result['all_trades'])
        if len(trades_df) > 0:
            trades_df = trades_df.sort_values('exit_date', ascending=False)
            
            for i, trade in trades_df.head(10).iterrows():
                print(f"[{trade['ticker']}] "
                      f"{trade['entry_date'].strftime('%Y-%m-%d')} → "
                      f"{trade['exit_date'].strftime('%Y-%m-%d')} "
                      f"({trade['holding_days']}일) "
                      f"수익률:{trade['return']*100:7.2f}% "
                      f"사유:{trade['exit_reason']}")
        
        print("=" * 80)


def run_additional_analysis(results: Dict):
    """추가 분석: 매도 사유별 및 종목별 성과 분석"""
    
    # 매도 사유별 분석
    if results['all_trades']:
        trades_df = pd.DataFrame(results['all_trades'])
        
        print("\n" + "=" * 80)
        print("추가 분석")
        print("=" * 80)
        
        print("\n📊 매도 사유별 통계")
        print("-" * 60)
        
        exit_reason_stats = trades_df.groupby('exit_reason').agg({
            'return': ['count', 'mean', 'std'],
            'profit': 'sum',
            'holding_days': 'mean'
        }).round(4)
        
        print(exit_reason_stats)
        
        print("\n📋 매도 사유별 분포")
        print(trades_df['exit_reason'].value_counts())
        
        print("\n💰 매도 사유별 평균 수익률")
        print(trades_df.groupby('exit_reason')['return'].mean().sort_values(ascending=False) * 100)
    
    # 종목별 성과 분석
    if results['individual_results']:
        performance = pd.DataFrame([
            {
                'ticker': r['ticker'],
                'name': r['name'],
                'trades': len(r['trades']),
                'total_return': r['total_return'] * 100
            }
            for r in results['individual_results']
        ])
        
        performance = performance.sort_values('total_return', ascending=False)
        
        print("\n📈 종목별 전체 성과")
        print("-" * 80)
        print(performance.to_string(index=False))
        
        print(f"\n✅ 수익 종목: {len(performance[performance['total_return'] > 0])}개")
        print(f"❌ 손실 종목: {len(performance[performance['total_return'] < 0])}개")
        print(f"📊 평균 수익률: {performance['total_return'].mean():.2f}%")


def _compute_metrics(trades_df: pd.DataFrame, initial_capital: int) -> Dict:
    """성과 지표 계산 (시각화 + 출력 공용)"""
    ts = trades_df.sort_values('exit_date').copy()
    ts['cum_profit'] = ts['profit'].cumsum()
    ts['equity'] = initial_capital + ts['cum_profit']

    equity = ts['equity']
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    total_days = (ts['exit_date'].max() - ts['entry_date'].min()).days
    total_return = (equity.iloc[-1] / initial_capital) - 1
    cagr = (1 + total_return) ** (365 / max(total_days, 1)) - 1 if total_days > 0 else 0

    tr = ts['return']
    avg_holding = ts['holding_days'].mean()
    ann = 252 / max(avg_holding, 1)
    sharpe = tr.mean() / tr.std() * np.sqrt(ann) if tr.std() > 0 else 0

    mdd = drawdown.min()
    calmar = cagr / abs(mdd) if mdd != 0 else 0

    wins = (tr > 0).astype(int)
    streaks = wins.groupby((wins != wins.shift()).cumsum())
    max_win_streak = streaks.apply(lambda x: len(x) if x.iloc[0] == 1 else 0).max()
    max_loss_streak = streaks.apply(lambda x: len(x) if x.iloc[0] == 0 else 0).max()

    win_count = (tr > 0).sum()
    loss_count = (tr < 0).sum()
    win_rate = win_count / len(tr) if len(tr) > 0 else 0
    avg_win = tr[tr > 0].mean() if win_count > 0 else 0
    avg_loss = tr[tr < 0].mean() if loss_count > 0 else 0
    profit_factor = abs(avg_win * win_count / (avg_loss * loss_count)) if loss_count > 0 else float('inf')

    # 누적 승률 시리즈
    ts['cum_win_rate'] = wins.expanding().mean()

    return {
        'ts': ts, 'equity': equity, 'drawdown': drawdown,
        'total_return': total_return, 'cagr': cagr, 'mdd': mdd,
        'sharpe': sharpe, 'calmar': calmar,
        'total_trades': len(tr), 'win_count': win_count, 'loss_count': loss_count,
        'win_rate': win_rate, 'avg_win': avg_win, 'avg_loss': avg_loss,
        'profit_factor': profit_factor, 'total_profit': ts['profit'].sum(),
        'max_win_streak': max_win_streak, 'max_loss_streak': max_loss_streak,
        'avg_holding': avg_holding, 'total_days': total_days,
        'max_return': tr.max(), 'min_return': tr.min(),
    }


# ─── 공용 스타일 상수 ────────────────────────────────────────
_C = {
    'bg': '#0e1117', 'card': '#1a1f2e', 'text': '#e6eaf0',
    'green': '#00d26a', 'red': '#f5365c', 'blue': '#3b82f6',
    'orange': '#f59e0b', 'purple': '#8b5cf6', 'gray': '#6b7280',
    'grid': '#2d3348',
}

REASON_KO = {
    'universe_exit': '유니버스 이탈', 'cci_exit': 'CCI < -100',
    'macd_dead': 'MACD 데드크로스', 'price_below_bb': 'BB 중심선 이탈',
    'stop_loss': '손절매', 'take_profit': '익절매', 'end_of_period': '기간 종료',
}


def _style_ax(ax, title='', xlabel='', ylabel=''):
    """공용 축 스타일 적용"""
    ax.set_facecolor(_C['bg'])
    ax.set_title(title, color=_C['text'], fontsize=12, fontweight='bold', pad=10)
    ax.set_xlabel(xlabel, color=_C['gray'], fontsize=9)
    ax.set_ylabel(ylabel, color=_C['gray'], fontsize=9)
    ax.tick_params(colors=_C['gray'], labelsize=8)
    ax.grid(color=_C['grid'], alpha=0.4, linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_color(_C['grid'])


def visualize_results(results: Dict, initial_capital: int = 10000000):
    """백테스트 결과 시각화 (2-page 대시보드)"""
    if not results['all_trades']:
        print("거래 내역이 없어 시각화를 생략합니다.")
        return

    trades_df = pd.DataFrame(results['all_trades'])
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])

    m = _compute_metrics(trades_df, initial_capital)
    ts = m['ts']

    # ════════════════════════════════════════════════════════════
    #  PAGE 1: 핵심 차트
    # ════════════════════════════════════════════════════════════
    fig, axes = plt.subplots(2, 2, figsize=(16, 10),
                             gridspec_kw={'height_ratios': [1.6, 1]})
    fig.patch.set_facecolor(_C['bg'])
    fig.suptitle('Momentum Strategy Backtest  |  Credit-Ratio Universe Filter',
                 color=_C['text'], fontsize=14, fontweight='bold', y=0.98)

    # ── 1-1. Equity Curve + Drawdown ──
    ax = axes[0, 0]
    _style_ax(ax, title='Equity Curve & Drawdown', ylabel='Equity (KRW)')
    ax.plot(ts['exit_date'], ts['equity'], color=_C['blue'], linewidth=1.4, label='Equity')
    ax.fill_between(ts['exit_date'], initial_capital, ts['equity'],
                    where=ts['equity'] >= initial_capital, alpha=0.10, color=_C['green'])
    ax.fill_between(ts['exit_date'], initial_capital, ts['equity'],
                    where=ts['equity'] < initial_capital, alpha=0.10, color=_C['red'])
    ax.axhline(initial_capital, color=_C['gray'], ls='--', lw=0.7)

    ax2 = ax.twinx()
    ax2.fill_between(ts['exit_date'], m['drawdown'] * 100, 0,
                     color=_C['red'], alpha=0.20)
    ax2.set_ylabel('Drawdown (%)', color=_C['gray'], fontsize=9)
    ax2.tick_params(colors=_C['gray'], labelsize=8)
    ax2.set_ylim(m['mdd'] * 100 * 1.5, 5)
    ax2.spines['right'].set_color(_C['grid'])

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    ax.legend(loc='upper left', fontsize=8, facecolor=_C['card'],
              edgecolor=_C['grid'], labelcolor=_C['text'])

    # ── 1-2. 수익률 분포 ──
    ax = axes[0, 1]
    _style_ax(ax, title='Return Distribution', xlabel='Return (%)', ylabel='Count')
    ret_pct = trades_df['return'] * 100
    n, bins, patches = ax.hist(ret_pct, bins=30, edgecolor=_C['bg'], linewidth=0.5)
    for patch, left in zip(patches, bins[:-1]):
        patch.set_facecolor(_C['green'] if left >= 0 else _C['red'])
        patch.set_alpha(0.75)
    ax.axvline(ret_pct.mean(), color=_C['orange'], ls='--', lw=1.2,
               label=f'Mean {ret_pct.mean():.2f}%')
    ax.axvline(ret_pct.median(), color=_C['purple'], ls=':', lw=1.2,
               label=f'Median {ret_pct.median():.2f}%')
    ax.legend(fontsize=8, facecolor=_C['card'], edgecolor=_C['grid'], labelcolor=_C['text'])

    # ── 1-3. 매도 사유 도넛 + 바 ──
    ax = axes[1, 0]
    ax.set_facecolor(_C['bg'])
    reason_counts = trades_df['exit_reason'].value_counts()
    labels = [REASON_KO.get(r, r) for r in reason_counts.index]
    palette = [_C['red'], _C['blue'], _C['orange'], _C['purple'],
               _C['green'], _C['gray'], '#ec4899'][:len(reason_counts)]

    wedges, texts, autotexts = ax.pie(
        reason_counts.values, labels=labels, autopct='%1.1f%%',
        startangle=140, pctdistance=0.78, colors=palette,
        wedgeprops=dict(width=0.45, edgecolor=_C['bg'], linewidth=2))
    for t in texts:
        t.set_color(_C['text'])
        t.set_fontsize(9)
    for t in autotexts:
        t.set_color('white')
        t.set_fontsize(8)
        t.set_fontweight('bold')
    ax.set_title('Exit Reason Distribution', color=_C['text'],
                 fontsize=12, fontweight='bold', pad=10)

    # ── 1-4. 월별 손익 히트맵 ──
    ax = axes[1, 1]
    _style_ax(ax, title='Monthly P&L (KRW)')
    tmp = ts.copy()
    tmp['year'] = tmp['exit_date'].dt.year
    tmp['month'] = tmp['exit_date'].dt.month
    pivot = tmp.groupby(['year', 'month'])['profit'].sum().reset_index()
    pivot = pivot.pivot_table(index='year', columns='month', values='profit', aggfunc='sum')
    pivot = pivot.reindex(columns=range(1, 13))

    vmax = max(abs(np.nanmin(pivot.values)), abs(np.nanmax(pivot.values))) / 1e4
    im = ax.imshow(pivot.values / 1e4, cmap='RdYlGn', aspect='auto',
                   vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels([f'{m}' for m in range(1, 13)], fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    cb = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.ax.tick_params(labelsize=7, colors=_C['gray'])
    cb.set_label('만원', fontsize=8, color=_C['gray'])
    for r in range(pivot.shape[0]):
        for c in range(pivot.shape[1]):
            val = pivot.values[r, c]
            if not np.isnan(val):
                txt_color = 'white' if abs(val / 1e4) > vmax * 0.5 else _C['text']
                ax.text(c, r, f'{val/1e4:,.0f}', ha='center', va='center',
                        fontsize=7, color=txt_color, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.subplots_adjust(hspace=0.35, wspace=0.30)
    plt.show()

    # ════════════════════════════════════════════════════════════
    #  PAGE 2: 성과 대시보드
    # ════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(16, 9))
    fig.patch.set_facecolor(_C['bg'])
    fig.suptitle('Performance Dashboard',
                 color=_C['text'], fontsize=14, fontweight='bold', y=0.98)

    gs = fig.add_gridspec(3, 4, hspace=0.45, wspace=0.35,
                          left=0.06, right=0.97, top=0.90, bottom=0.08)

    # ── 2-top: KPI 카드 (8개) ──
    kpis = [
        ('Total Return', f"{m['total_return']*100:+.2f}%", m['total_return'] >= 0),
        ('CAGR', f"{m['cagr']*100:+.2f}%", m['cagr'] >= 0),
        ('MDD', f"{m['mdd']*100:.2f}%", False),
        ('Sharpe', f"{m['sharpe']:.2f}", m['sharpe'] >= 1),
        ('Win Rate', f"{m['win_rate']*100:.1f}%", m['win_rate'] >= 0.5),
        ('Profit Factor', f"{m['profit_factor']:.2f}", m['profit_factor'] >= 1),
        ('Trades', f"{m['total_trades']}", True),
        ('Avg Hold', f"{m['avg_holding']:.0f}d", True),
    ]
    for col, (label, value, is_good) in enumerate(kpis):
        ax = fig.add_subplot(gs[0, col]) if col < 4 else fig.add_subplot(gs[1, col - 4])
        ax.set_facecolor(_C['card'])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        for spine in ax.spines.values():
            spine.set_visible(False)

        accent = _C['green'] if is_good else _C['red']
        ax.text(0.5, 0.65, value, ha='center', va='center',
                fontsize=18, fontweight='bold', color=accent,
                transform=ax.transAxes)
        ax.text(0.5, 0.25, label, ha='center', va='center',
                fontsize=9, color=_C['gray'], transform=ax.transAxes)

        rect = plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                              facecolor=_C['card'], edgecolor=_C['grid'],
                              linewidth=1, zorder=0, clip_on=False)
        ax.add_patch(rect)

    # KPI 2행 (나머지 4개)
    for col in range(4):
        idx = col + 4
        if idx >= len(kpis):
            break
        label, value, is_good = kpis[idx]
        ax = fig.add_subplot(gs[1, col])
        ax.set_facecolor(_C['card'])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        accent = _C['green'] if is_good else _C['red']
        ax.text(0.5, 0.65, value, ha='center', va='center',
                fontsize=18, fontweight='bold', color=accent, transform=ax.transAxes)
        ax.text(0.5, 0.25, label, ha='center', va='center',
                fontsize=9, color=_C['gray'], transform=ax.transAxes)
        rect = plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                              facecolor=_C['card'], edgecolor=_C['grid'],
                              linewidth=1, zorder=0, clip_on=False)
        ax.add_patch(rect)

    # ── 2-bottom-left: 보유기간 vs 수익률 ──
    ax = fig.add_subplot(gs[2, :2])
    _style_ax(ax, title='Holding Period vs Return', xlabel='Days', ylabel='Return (%)')
    sc = ax.scatter(trades_df['holding_days'], trades_df['return'] * 100,
                    c=trades_df['return'].apply(lambda x: _C['green'] if x > 0 else _C['red']),
                    alpha=0.6, s=20, edgecolors='none')
    ax.axhline(0, color=_C['gray'], lw=0.6)

    # ── 2-bottom-right: 누적 승률 추이 ──
    ax = fig.add_subplot(gs[2, 2:])
    _style_ax(ax, title='Cumulative Win Rate', xlabel='Trade #', ylabel='Win Rate (%)')
    ax.plot(range(1, len(ts) + 1), ts['cum_win_rate'] * 100,
            color=_C['blue'], linewidth=1.3)
    ax.axhline(50, color=_C['gray'], ls='--', lw=0.7)
    ax.fill_between(range(1, len(ts) + 1), 50, ts['cum_win_rate'] * 100,
                    where=ts['cum_win_rate'] * 100 >= 50,
                    alpha=0.10, color=_C['green'])
    ax.fill_between(range(1, len(ts) + 1), 50, ts['cum_win_rate'] * 100,
                    where=ts['cum_win_rate'] * 100 < 50,
                    alpha=0.10, color=_C['red'])
    ax.set_ylim(0, 100)

    plt.show()

    # ── 콘솔 성과 요약 ──
    _print_performance_summary(m)


def _print_performance_summary(m: Dict):
    """성과 지표 콘솔 출력"""
    W = 62
    line = '-' * W
    dline = '=' * W

    print(f"\n{dline}")
    print(f"{'PERFORMANCE SUMMARY':^{W}}")
    print(dline)

    print(f"\n  {'[ Returns ]':^{W}}")
    print(f"  {'Total Return':<22} {m['total_return']*100:>12.2f} %")
    print(f"  {'CAGR':<22} {m['cagr']*100:>12.2f} %")
    print(f"  {'Total Profit':<22} {m['total_profit']:>12,.0f} KRW")

    print(f"\n  {'[ Risk ]':^{W}}")
    print(f"  {'MDD':<22} {m['mdd']*100:>12.2f} %")
    print(f"  {'Sharpe Ratio':<22} {m['sharpe']:>12.2f}")
    print(f"  {'Calmar Ratio':<22} {m['calmar']:>12.2f}")

    print(f"\n  {'[ Trades ]':^{W}}")
    print(f"  {'Total Trades':<22} {m['total_trades']:>12d}")
    print(f"  {'Win / Loss':<22} {m['win_count']:>5d} / {m['loss_count']:<5d}")
    print(f"  {'Win Rate':<22} {m['win_rate']*100:>12.1f} %")
    print(f"  {'Profit Factor':<22} {m['profit_factor']:>12.2f}")
    print(f"  {'Avg Win':<22} {m['avg_win']*100:>12.2f} %")
    print(f"  {'Avg Loss':<22} {m['avg_loss']*100:>12.2f} %")
    print(f"  {'Best Trade':<22} {m['max_return']*100:>12.2f} %")
    print(f"  {'Worst Trade':<22} {m['min_return']*100:>12.2f} %")

    print(f"\n  {'[ Streaks & Holding ]':^{W}}")
    print(f"  {'Max Win Streak':<22} {m['max_win_streak']:>12.0f}")
    print(f"  {'Max Loss Streak':<22} {m['max_loss_streak']:>12.0f}")
    print(f"  {'Avg Holding Days':<22} {m['avg_holding']:>12.1f}")
    print(f"  {'Total Period':<22} {m['total_days']:>12d} days")
    print(dline)


# ═══════════════════════════════════════════════════════════════
#  파라미터 최적화
# ═══════════════════════════════════════════════════════════════

PARAM_COMBOS = [
    {'label': 'CCI14 + MACD 표준(12,26,9)', 'cci_period': 14, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9},
    {'label': 'CCI14 + MACD 빠른(8,21,7)',  'cci_period': 14, 'macd_fast': 8,  'macd_slow': 21, 'macd_signal': 7},
    {'label': 'CCI20 + MACD 표준(12,26,9)', 'cci_period': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9},
    {'label': 'CCI20 + MACD 빠른(8,21,7)',  'cci_period': 20, 'macd_fast': 8,  'macd_slow': 21, 'macd_signal': 7},
]


def run_optimization(csv_path: str, unified_csv_path: str) -> List[Dict]:
    """4가지 파라미터 조합에 대한 백테스트 실행"""
    opt_results = []

    for idx, combo in enumerate(PARAM_COMBOS, 1):
        print(f"\n{'='*80}")
        print(f"[{idx}/4] 파라미터 조합: {combo['label']}")
        print(f"{'='*80}")

        backtester = LocalCSVBacktester(csv_path, unified_csv_path)
        results = backtester.run_portfolio_backtest(
            cci_period=combo['cci_period'],
            macd_fast=combo['macd_fast'],
            macd_slow=combo['macd_slow'],
            macd_signal=combo['macd_signal'],
        )

        # 성과 지표 계산
        metrics = {}
        if results['all_trades']:
            trades_df = pd.DataFrame(results['all_trades'])
            trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
            trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])
            metrics = _compute_metrics(trades_df, 10_000_000)

        opt_results.append({
            'label': combo['label'],
            'combo': combo,
            'results': results,
            'metrics': metrics,
        })

    return opt_results


def print_optimization_comparison(opt_results: List[Dict]):
    """파라미터 조합 비교 테이블 콘솔 출력"""
    W = 90
    dline = '=' * W

    print(f"\n{dline}")
    print(f"{'PARAMETER OPTIMIZATION COMPARISON':^{W}}")
    print(dline)

    # 헤더
    header = f"  {'Combination':<30} {'Return':>9} {'CAGR':>8} {'MDD':>8} {'Sharpe':>7} {'WinRate':>8} {'PF':>6} {'Trades':>7} {'AvgHold':>8}"
    print(header)
    print('-' * W)

    best_idx = -1
    best_sharpe = -999

    for i, opt in enumerate(opt_results):
        m = opt['metrics']
        if not m:
            print(f"  {opt['label']:<30} {'N/A':>9}")
            continue

        line = (f"  {opt['label']:<30} "
                f"{m['total_return']*100:>+8.2f}% "
                f"{m['cagr']*100:>+7.2f}% "
                f"{m['mdd']*100:>7.2f}% "
                f"{m['sharpe']:>7.2f} "
                f"{m['win_rate']*100:>7.1f}% "
                f"{m['profit_factor']:>6.2f} "
                f"{m['total_trades']:>7d} "
                f"{m['avg_holding']:>7.1f}d")
        print(line)

        if m['sharpe'] > best_sharpe:
            best_sharpe = m['sharpe']
            best_idx = i

    print(dline)
    if best_idx >= 0:
        best = opt_results[best_idx]
        print(f"\n  >> 최적 조합 (Sharpe 기준): {best['label']}")
        bm = best['metrics']
        print(f"     Total Return: {bm['total_return']*100:+.2f}%  |  "
              f"CAGR: {bm['cagr']*100:+.2f}%  |  "
              f"MDD: {bm['mdd']*100:.2f}%  |  "
              f"Sharpe: {bm['sharpe']:.2f}")
    print()


def visualize_optimization(opt_results: List[Dict], initial_capital: int = 10_000_000):
    """파라미터 조합 비교 시각화 (다크 테마)"""
    # 유효한 결과만 필터
    valid = [o for o in opt_results if o['metrics']]
    if not valid:
        print("시각화할 결과가 없습니다.")
        return

    colors = [_C['blue'], _C['orange'], _C['green'], _C['purple']]

    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor(_C['bg'])
    fig.suptitle('Parameter Optimization  |  CCI Period × MACD Params',
                 color=_C['text'], fontsize=14, fontweight='bold', y=0.98)

    gs = fig.add_gridspec(2, 2, hspace=0.40, wspace=0.30,
                          left=0.07, right=0.96, top=0.91, bottom=0.08)

    # ── 1. Equity Curve 비교 ──
    ax = fig.add_subplot(gs[0, :])
    _style_ax(ax, title='Equity Curve Comparison', ylabel='Equity (KRW)')
    for i, opt in enumerate(valid):
        ts = opt['metrics']['ts']
        ax.plot(ts['exit_date'], ts['equity'],
                color=colors[i % len(colors)], linewidth=1.4,
                label=opt['label'], alpha=0.9)
    ax.axhline(initial_capital, color=_C['gray'], ls='--', lw=0.7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    ax.legend(fontsize=9, facecolor=_C['card'], edgecolor=_C['grid'],
              labelcolor=_C['text'], loc='upper left')

    # ── 2. Total Return 비교 바 차트 ──
    ax = fig.add_subplot(gs[1, 0])
    _style_ax(ax, title='Total Return (%)', ylabel='%')
    labels = [o['label'] for o in valid]
    vals = [o['metrics']['total_return'] * 100 for o in valid]
    bar_colors = [_C['green'] if v >= 0 else _C['red'] for v in vals]
    bars = ax.bar(range(len(vals)), vals, color=bar_colors, alpha=0.8, width=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7, rotation=15, ha='right')
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f'{v:+.2f}%', ha='center', va='bottom',
                color=_C['text'], fontsize=9, fontweight='bold')

    # ── 3. 핵심 KPI 레이더 스타일 비교 (그룹 바 차트) ──
    ax = fig.add_subplot(gs[1, 1])
    _style_ax(ax, title='Key Metrics Comparison')

    kpi_names = ['Sharpe', 'Win Rate(%)', 'Profit Factor']
    x = np.arange(len(kpi_names))
    n_combos = len(valid)
    width = 0.18

    for i, opt in enumerate(valid):
        m = opt['metrics']
        kpi_vals = [m['sharpe'], m['win_rate'] * 100, m['profit_factor']]
        offset = (i - n_combos / 2 + 0.5) * width
        ax.bar(x + offset, kpi_vals, width, color=colors[i % len(colors)],
               alpha=0.8, label=opt['label'])

    ax.set_xticks(x)
    ax.set_xticklabels(kpi_names, fontsize=9, color=_C['text'])
    ax.legend(fontsize=7, facecolor=_C['card'], edgecolor=_C['grid'],
              labelcolor=_C['text'])

    plt.show()


def main():
    """메인 실행 함수 — 파라미터 최적화 모드"""
    # CSV 파일 경로 설정
    csv_path = r"C:\Users\jeeho\Desktop\pj3\project3\ohlcv_data.csv"
    unified_csv_path = r"C:\Users\jeeho\Desktop\pj3\project3\김동호\unified_data.csv"

    print("\n" + "=" * 80)
    print("모멘텀 전략 파라미터 최적화 (신용비율 유니버스 필터 적용)")
    print("=" * 80)
    print("\n비교 조합:")
    for i, c in enumerate(PARAM_COMBOS, 1):
        print(f"  {i}. {c['label']}")
    print()

    # 4개 파라미터 조합 최적화 실행
    opt_results = run_optimization(csv_path, unified_csv_path)

    # 비교 테이블 출력
    print_optimization_comparison(opt_results)

    # 비교 시각화
    visualize_optimization(opt_results)

    # 최적 조합에 대한 상세 결과 출력 및 시각화
    valid = [o for o in opt_results if o['metrics']]
    if valid:
        best = max(valid, key=lambda o: o['metrics']['sharpe'])
        print(f"\n{'='*80}")
        print(f"최적 조합 상세 분석: {best['label']}")
        print(f"{'='*80}")
        visualize_results(best['results'])

        # 최적 조합 거래 내역 CSV 저장
        output_path = r"C:\Users\jeeho\Desktop\pj3\project3\Backtest\ex\backtest_trades_best.csv"
        if best['results']['all_trades']:
            trades_df = pd.DataFrame(best['results']['all_trades'])
            trades_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            print(f"\n최적 조합 거래 내역 저장: {output_path}")


if __name__ == "__main__":
    main()
