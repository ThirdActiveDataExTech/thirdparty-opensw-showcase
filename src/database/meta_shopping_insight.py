"""meta_shopping_insight / active_meta_shopping_insight 읽기·쓰기 헬퍼."""

from typing import Any, Dict, List, Optional

from src.database.db import get_conn


def get_meta_shopping_insight_rows(dataset_id: str) -> List[Dict[str, Any]]:
    """이 dataset_id에 등록된 전체 카테고리(anchor 포함)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, category_id, category_name, is_anchor
            FROM meta_shopping_insight
            WHERE dataset_id = %s
            """,
            (dataset_id,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_last_period(dataset_id: str) -> Optional[str]:
    """이 dataset_id의 카테고리 중 가장 최근 수집된 period. 데이터 없으면 None.

    overlap 윈도우 계산(파이프라인)의 기준점 — 이 날짜에서 며칠 전부터 다시
    가져와야 inter_scale 계산에 쓸 겹치는 기간이 생긴다.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MAX(a.period) FROM active_meta_shopping_insight a
            JOIN meta_shopping_insight m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        row = cur.fetchone()
        return row[0].isoformat() if row and row[0] else None
    finally:
        conn.close()


def get_existing_anchor_raw(
    anchor_meta_id: int, gender: str, age: str, periods: List[str]
) -> Dict[str, float]:
    """anchor 카테고리의 기존(DB에 이미 저장된) raw_ratio — {period: raw_ratio}.

    inter_scale 계산에 쓰인다. periods가 비어있으면 빈 dict 반환.
    """
    if not periods:
        return {}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT period, raw_ratio FROM active_meta_shopping_insight
            WHERE meta_id = %s AND gender = %s AND age = %s
              AND period = ANY(%s::date[])
            """,
            (anchor_meta_id, gender, age, periods),
        )
        return {row[0].isoformat(): row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def upsert_active_meta_shopping_insight(
    meta_id: int,
    period: str,
    gender: str,
    age: str,
    raw_ratio: float,
    anchor_raw_ratio: Optional[float],
    normalized_ratio: Optional[float],
    scale_factor: float,
    pseudo_volume: float,
    batch_index: int,
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO active_meta_shopping_insight
                (meta_id, period, gender, age, raw_ratio, anchor_raw_ratio,
                 normalized_ratio, scale_factor, pseudo_volume, batch_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (meta_id, period, gender, age) DO UPDATE SET
                raw_ratio = EXCLUDED.raw_ratio,
                anchor_raw_ratio = EXCLUDED.anchor_raw_ratio,
                normalized_ratio = EXCLUDED.normalized_ratio,
                scale_factor = EXCLUDED.scale_factor,
                pseudo_volume = EXCLUDED.pseudo_volume,
                batch_index = EXCLUDED.batch_index,
                collected_at = now()
            """,
            (
                meta_id, period, gender, age, raw_ratio, anchor_raw_ratio,
                normalized_ratio, scale_factor, pseudo_volume, batch_index,
            ),
        )
        conn.commit()
    finally:
        conn.close()
