"""
Macro Regime Analysis Package
================================
KOSPI200 지수 기반 레짐 분석 시스템

Main Components:
- KISIndexAPI: 한국투자증권 API 클라이언트
- RegimeClassifier: 레짐 분류기
- main(): 메인 실행 함수

Usage:
    # 직접 실행
    python live_regime_check_v1.py

    # 또는 모듈로 import (옵션)
    from Macro.live_regime_check_v1 import main, KISIndexAPI
"""

__version__ = "1.0.0"
__author__ = "Your Name"

# 선택사항: 자주 사용하는 클래스/함수 노출
# from .live_regime_check_v1 import KISIndexAPI, RegimeClassifier, main

__all__ = []  # 비워두면 명시적으로 import해야 함
