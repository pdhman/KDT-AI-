import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict
from tabulate import tabulate

# ==========================================
# 1. Universe Construction
# ==========================================

def build_universe_from_csv(
    path: str,
    min_cap: float = 3000,
    top_n_liq: int = 500,
    verbose: bool = True
) -> pd.DataFrame:
    """
    CSV 기반 유니버스 생성 함수
    """

    df = pd.read_csv(path)

    cond_cap = df['시가총액(억)'] >= min_cap
    thresh_liq = df['거래대금 (5일평균 억)'].nlargest(top_n_liq).min()
    cond_liq = df['거래대금 (5일평균 억)'] >= thresh_liq

    cond_safe = (
        (df['관리종목 =1'] != 1) &
        (df['스팩 =1'] != 1) &
        (df['리츠 =1'] != 1) &
        (df['적자기업 =1'] != 1)
    )

    universe = df[cond_cap & cond_liq & cond_safe].copy()

    if verbose:
        print(f"필터링 전: {len(df)}개 -> 필터링 후: {len(universe)}개")

    return universe

# ==========================================
# 2. Statistical Transformations
# ==========================================

def calculate_zscore(
    df: pd.DataFrame,
    columns: List[str],
    output_suffix: str = '_z',
    handle_zero_std: str = 'zero'
) -> pd.DataFrame:
    """
    지정된 컬럼들의 z-score 계산
    z-score 컬럼이 추가된 데이터프레임 pd.DataFrame 반환
    """
    df = df.copy()

    for col in columns:
        mu = df[col].mean()
        sigma = df[col].std(ddof=1)
        output_col = f'{col}{output_suffix}'

        if sigma == 0 or np.isnan(sigma):
            if handle_zero_std == 'zero':
                df[output_col] = 0
            elif handle_zero_std == 'nan':
                df[output_col] = np.nan
            # 'drop'의 경우 컬럼을 생성하지 않음
        else:
            df[output_col] = (df[col] - mu) / sigma

    return df


def calculate_delta(
    df: pd.DataFrame,
    col_pairs: List[Tuple[str, str]],
    output_names: List[str]
) -> pd.DataFrame:
    """
    두 컬럼 간의 증가분 계산
    """
    df = df.copy()

    if len(col_pairs) != len(output_names):
        raise ValueError("col_pairs와 output_names의 길이가 일치해야 합니다.")

    for (col_current, col_past), output_name in zip(col_pairs, output_names):
        df[output_name] = df[col_current] - df[col_past]

    return df

# ==========================================
# 3. Scoring Functions
# ==========================================

def calculate_earnings_score(
    df: pd.DataFrame,
    growth_cols: List[str],
    delta_cols: List[str],
    weights: Optional[Dict[str, float]] = None,
    output_col: str = 'z_score_growth'
) -> pd.DataFrame:
    """
    스코어 계산
    """
    df = df.copy()

    # 1. 성장률 z-score
    df = calculate_zscore(df, growth_cols, output_suffix='_z')

    # 2. 증가분 z-score
    df = calculate_zscore(df, delta_cols, output_suffix='_z')

    # 3. 가중치 설정
    if weights is None:
        all_cols = [f'{col}_z' for col in growth_cols + delta_cols]
        weights = {col: 1.0 / len(all_cols) for col in all_cols}

    # 4. 종합 스코어 계산
    df[output_col] = sum(df[col] * weight for col, weight in weights.items() if weight != 0)

    return df


# ==========================================
# 4. Selection & Ranking
# ==========================================

def select_top_stocks(
    df: pd.DataFrame,
    score_col: str,
    top_n: int = 30,
    rank_col: str = '통합순위',
    ascending: bool = False
) -> pd.DataFrame:
    """
    스코어 기준 상위 N개 종목 선정 및 순위 부여
    """

    df_sorted = df.sort_values(score_col, ascending=ascending).head(top_n).copy()
    df_sorted[rank_col] = range(1, len(df_sorted) + 1)

    return df_sorted

# ==========================================
# 5. Display & Export
# ==========================================

def print_portfolio_table(
    df: pd.DataFrame,
    display_cols: List[str],
    top_n: int = 20,
    sort_col: Optional[str] = None,
    ascending: bool = False,
    tablefmt: str = 'psql'
) -> None:
    """
    포트폴리오 결과를 테이블 형태로 출력
    """
    if sort_col:
        print_df = df.sort_values(sort_col, ascending=ascending).head(top_n)
    else:
        print_df = df.head(top_n)

    print(tabulate(print_df[display_cols], headers='keys', tablefmt=tablefmt, 
                   floatfmt=".2f", showindex=False))


