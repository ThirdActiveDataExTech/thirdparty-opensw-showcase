"""Naver DataLab pseudo_volume 보정 수학 — 순수 함수, DB/네트워크 접근 없음.

레거시(3amd/naver_shopping_insight.py)의 compute_scale_factor/_median_ratio를
포팅했다. 원래는 DB에서 직접 조회했지만, collectors/는 DB에 접근하지 않는다는
레이어 규칙에 맞춰 "기존 anchor 값"을 인자로 받는 순수 함수로 바꿨다 — DB 조회는
pipelines 레이어가 담당한다.

shopping_insight(P01 연구 주제와 직결)뿐 아니라 persona_insight(Phase 2)의
stacked-median 보정에도 median_ratio를 그대로 재사용할 수 있게 별도 모듈로 뺐다.
"""

from typing import Dict


def median_ratio(a: Dict[str, float], b: Dict[str, float]) -> float:
    """두 {period: raw} 딕셔너리에서 a[t]/b[t]의 중앙값. 겹치는 유효 데이터 없으면 1.0."""
    ratios = [a[t] / b[t] for t in a if t in b and b[t] > 0 and a[t] > 0]
    if not ratios:
        return 1.0
    ratios.sort()
    n = len(ratios)
    return ratios[n // 2] if n % 2 == 1 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2


def compute_inter_scale(
    existing_anchor_by_period: Dict[str, float],
    new_anchor_by_period: Dict[str, float],
) -> float:
    """수집 구간 간 보정 계수 — 겹치는 기간에서 (기존 raw / 신규 raw) 중앙값.

    기존 데이터가 없으면(=첫 수집) 1.0.
    """
    if not existing_anchor_by_period or not new_anchor_by_period:
        return 1.0
    ratios = [
        old / new_anchor_by_period[period]
        for period, old in existing_anchor_by_period.items()
        if period in new_anchor_by_period
        and new_anchor_by_period[period] > 0
        and old > 0
    ]
    if not ratios:
        return 1.0
    ratios.sort()
    n = len(ratios)
    return ratios[n // 2] if n % 2 == 1 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
