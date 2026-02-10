#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
매크로(거시경제) 지표 1. USD/KRW vs KOSPI: 음(-)의 상관관계(디커플링)
---------------------------------------------------------------------

[운용사(퀀트/리스크) 관점]
- 환율(달러/원, USD/KRW)은 한국 주식에 대해 흔히 '리스크 프록시'로 작동합니다.
  * USD/KRW 상승(원화 약세) = 글로벌/국내 위험회피(Risk-Off) 경향 강화 → 주식에 부담
  * USD/KRW 하락(원화 강세) = 위험선호(Risk-On) 및 외국인 수급 환경 개선 가능 → 주식에 우호적
- 다만 이 관계는 **항상 일정하지 않으며**, 국면(성장/금리/신용/수급)에 따라
  상관이 약해지거나 반대로 움직이기도 합니다. 본 스크립트는 레짐 변화를 데이터로 확인합니다.

[무엇을 계산하나?]
1) USD/KRW, KOSPI 지수(종가) 수집 후 정렬/정합
2) 일간(또는 월간) 수익률로 변환
3) 전체 구간 상관 + 최근 구간 상관 요약
4) 롤링 상관(기본 60영업일)로 '디커플링(음의 상관)' 구간 시각화
5) 산점도(수익률)로 관계를 직관적으로 확인
6) (추가) 코스피 '국지적 고점'과 달러/원 '국지적 저점'이 같은 날(또는 근접한 기간)에 발생한 지점을 표시

[주의(리스크/해석)]
- 상관은 과거의 동행 관계이며, 미래를 보장하지 않습니다.
- 환율-주가 관계는 원인/결과가 섞여 있을 수 있습니다(수급/정책/리스크 이벤트).
- 이벤트 구간에서는 상관이 급격히 뒤틀릴 수 있습니다.
- 교육/연구용 예시이며 투자자문이 아닙니다.

[데이터 소스]
- FinanceDataReader: 'USD/KRW' 환율, 'KS11' 코스피 지수 심볼 사용

실행 예시
- 기본(일간, 60일 롤링):  python usdkrw_kospi_decoupling.py
- 월간(12개월 롤링):      python usdkrw_kospi_decoupling.py --freq M --window 12
- 그림 저장:              python usdkrw_kospi_decoupling.py --save --outdir outputs
"""




from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import FinanceDataReader as fdr


# -----------------------------
# Font: Korean-friendly
# -----------------------------
def setup_korean_font() -> None:
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]
    available = {f.name for f in plt.matplotlib.font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def _to_date_str(x: str) -> str:
    x = x.strip()
    if len(x) == 4:
        return f"{x}-01-01"
    if len(x) == 7:
        return f"{x}-01"
    return x


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass
class Inputs:
    start: str
    end: str | None
    freq: str  # 'D' or 'M'
    window: int
    neg_threshold: float
    outdir: Path
    save: bool


def load_series(start: str, end: str | None) -> pd.DataFrame:
    fx = fdr.DataReader("USD/KRW", start, end)[["Close"]].rename(columns={"Close": "USDKRW"})
    kospi = fdr.DataReader("KS11", start, end)[["Close"]].rename(columns={"Close": "KOSPI"})
    df = fx.join(kospi, how="inner").dropna()
    if df.empty or df.shape[0] < 50:
        raise ValueError("데이터가 충분하지 않습니다. start/end를 확인하세요.")
    return df


def to_returns(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    x = df.copy()
    if freq.upper() == "M":
        x = x.resample("M").last()
    rets = np.log(x).diff().dropna()
    rets.columns = [c + "_RET" for c in rets.columns]
    return rets


def rolling_corr(rets: pd.DataFrame, window: int) -> pd.Series:
    s = rets["USDKRW_RET"].rolling(window).corr(rets["KOSPI_RET"])
    s.name = "ROLL_CORR"
    return s.dropna()


def summarize(rets: pd.DataFrame, roll: pd.Series) -> dict:
    out = {}
    out["corr_full"] = float(rets["USDKRW_RET"].corr(rets["KOSPI_RET"]))
    n = 252 if len(rets) > 260 else max(60, int(len(rets) * 0.25))
    recent = rets.iloc[-n:]
    out["corr_recent"] = float(recent["USDKRW_RET"].corr(recent["KOSPI_RET"]))
    out["pct_roll_negative"] = float((roll < 0).mean())
    out["pct_roll_below_-0.2"] = float((roll < -0.2).mean())
    out["latest_roll_corr"] = float(roll.iloc[-1])
    out["latest_date"] = str(roll.index[-1].date())
    return out


# -----------------------------
# Plots (separate)
# -----------------------------
def plot_levels(df: pd.DataFrame, title_suffix: str = "") -> plt.Figure:
    base = df.iloc[0]
    norm = df / base * 100.0

    fig = plt.figure(figsize=(13, 5))
    ax = fig.add_subplot(111)

    # 색상 구분 (요청 반영)
    ax.plot(norm.index, norm["KOSPI"], label="코스피 (정규화, 시작=100)", color="#1f77b4", linewidth=1.6)
    ax.set_ylabel("코스피 (정규화)")
    ax.grid(True, alpha=0.3)

    ax2 = ax.twinx()
    ax2.plot(norm.index, norm["USDKRW"], label="달러/원 (정규화, 시작=100)", color="#ff7f0e", linewidth=1.6)
    ax2.set_ylabel("달러/원 (정규화)")

    ax.set_title(f"레벨 비교 (정규화) {title_suffix}".strip())

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")

    fig.tight_layout()
    return fig


def plot_rolling_corr(roll: pd.Series, neg_threshold: float, window: int, title_suffix: str = "") -> plt.Figure:
    fig = plt.figure(figsize=(13, 4.5))
    ax = fig.add_subplot(111)

    ax.plot(roll.index, roll.values, label=f"롤링 상관 ({window})", color="#2ca02c", linewidth=1.6)
    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
    ax.axhline(neg_threshold, color="black", linewidth=1.0, alpha=0.8)

    below = roll < neg_threshold
    ax.fill_between(roll.index, roll.values, neg_threshold, where=below, color="#2ca02c", alpha=0.18)

    ax.set_title(f"달러/원-코스피 롤링 상관 (디커플링 구간 음영) {title_suffix}".strip())
    ax.set_ylabel("상관계수")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left")

    fig.tight_layout()
    return fig


def plot_scatter(rets: pd.DataFrame, title_suffix: str = "") -> plt.Figure:
    x = rets["USDKRW_RET"].values
    y = rets["KOSPI_RET"].values

    fig = plt.figure(figsize=(7, 6.5))
    ax = fig.add_subplot(111)

    ax.scatter(x, y, alpha=0.35, color="#9467bd")
    if len(x) > 2:
        b1, b0 = np.polyfit(x, y, 1)
        xs = np.linspace(np.nanmin(x), np.nanmax(x), 200)
        ax.plot(xs, b1 * xs + b0, linewidth=1.8, color="#d62728")

    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.7)
    ax.axvline(0.0, color="black", linewidth=1.0, alpha=0.7)

    corr = float(np.corrcoef(x, y)[0, 1])
    ax.set_title(f"수익률 산점도 (상관={corr:.3f}) {title_suffix}".strip())
    ax.set_xlabel("달러/원 로그수익률")
    ax.set_ylabel("코스피 로그수익률")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


# -----------------------------
# CLI / Main
# -----------------------------
def parse_args() -> Inputs:
    p = argparse.ArgumentParser(description="USD/KRW vs KOSPI 디커플링 분석 (3개 그림 분리/한글/색상 구분)")
    p.add_argument("--start", type=str, default="2010-01-01")
    p.add_argument("--end", type=str, default=None)
    p.add_argument("--freq", type=str, default="D", choices=["D", "M"])
    p.add_argument("--window", type=int, default=60)
    p.add_argument("--neg_threshold", type=float, default=-0.2)
    p.add_argument("--outdir", type=str, default="outputs")
    p.add_argument("--save", action="store_true")

    a = p.parse_args()
    return Inputs(
        start=_to_date_str(a.start),
        end=_to_date_str(a.end) if a.end else None,
        freq=a.freq.upper(),
        window=a.window,
        neg_threshold=float(a.neg_threshold),
        outdir=Path(a.outdir),
        save=bool(a.save),
    )


def main() -> None:
    setup_korean_font()
    args = parse_args()

    df = load_series(args.start, args.end)
    rets = to_returns(df, freq=args.freq)
    roll = rolling_corr(rets, window=args.window)
    summary = summarize(rets, roll)

    print("\n[PM-style summary]")
    print(f"- Sample: {rets.index.min().date()} ~ {rets.index.max().date()}  (n={len(rets)})  freq={args.freq}")
    print(f"- Corr (full):    {summary['corr_full']:.3f}")
    print(f"- Corr (recent):  {summary['corr_recent']:.3f}")
    print(f"- Rolling corr < 0:     {summary['pct_roll_negative']*100:.1f}%")
    print(f"- Rolling corr < -0.2:  {summary['pct_roll_below_-0.2']*100:.1f}%")
    print(f"- Latest rolling corr:  {summary['latest_roll_corr']:.3f}  @ {summary['latest_date']}")

    title_suffix = f"(freq={args.freq}, start={args.start})"

    fig1 = plot_levels(df, title_suffix=title_suffix)
    fig2 = plot_rolling_corr(roll, args.neg_threshold, args.window, title_suffix=title_suffix)
    fig3 = plot_scatter(rets, title_suffix=title_suffix)

    if args.save:
        _ensure_dir(args.outdir)
        p1 = args.outdir / f"01_levels_{args.freq}.png"
        p2 = args.outdir / f"02_rollcorr_{args.freq}_w{args.window}.png"
        p3 = args.outdir / f"03_scatter_{args.freq}.png"
        fig1.savefig(p1, dpi=180)
        fig2.savefig(p2, dpi=180)
        fig3.savefig(p3, dpi=180)
        print(f"\n[saved]\n- {p1}\n- {p2}\n- {p3}")

    plt.show()


if __name__ == "__main__":
    main()
