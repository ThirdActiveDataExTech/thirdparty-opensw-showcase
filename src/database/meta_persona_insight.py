"""meta_persona_insight / active_meta_persona_insight 읽기·쓰기 헬퍼."""

from typing import Any, Dict, List, Optional, Tuple

from src.database.db import get_conn


def get_meta_persona_insight_rows(dataset_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, category_id, category_name FROM meta_persona_insight WHERE dataset_id = %s",
            (dataset_id,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_last_period(dataset_id: str) -> Optional[str]:
    """이 dataset_id의 카테고리 중 가장 최근 수집된 period. 데이터 없으면 None."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MAX(a.period) FROM active_meta_persona_insight a
            JOIN meta_persona_insight m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        row = cur.fetchone()
        return row[0].isoformat() if row and row[0] else None
    finally:
        conn.close()


def get_existing_gender_ratios(meta_id: int, periods: List[str]) -> Dict[Tuple[str, str], float]:
    """{(period, gender): gender_ratio} — gender_scale(stacked inter_scale) 계산용."""
    if not periods:
        return {}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT period, gender, gender_ratio FROM active_meta_persona_insight
            WHERE meta_id = %s AND period = ANY(%s::date[])
            """,
            (meta_id, periods),
        )
        return {(row[0].isoformat(), row[1]): row[2] for row in cur.fetchall() if row[2] is not None}
    finally:
        conn.close()


def get_existing_age_ratios(meta_id: int, periods: List[str]) -> Dict[Tuple[str, str], float]:
    """{(period, age): age_ratio} — age_scale(stacked inter_scale) 계산용."""
    if not periods:
        return {}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT period, age, age_ratio FROM active_meta_persona_insight
            WHERE meta_id = %s AND period = ANY(%s::date[])
            """,
            (meta_id, periods),
        )
        return {(row[0].isoformat(), row[1]): row[2] for row in cur.fetchall() if row[2] is not None}
    finally:
        conn.close()


def upsert_active_meta_persona_insight(
    meta_id: int,
    period: str,
    gender: str,
    age: str,
    gender_ratio,
    age_ratio,
    gender_scale: float,
    age_scale: float,
    gender_pv,
    age_pv,
    persona_index,
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO active_meta_persona_insight
                (meta_id, period, gender, age, gender_ratio, age_ratio,
                 gender_scale, age_scale, gender_pv, age_pv, persona_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (meta_id, period, gender, age) DO UPDATE SET
                gender_ratio = EXCLUDED.gender_ratio,
                age_ratio = EXCLUDED.age_ratio,
                gender_scale = EXCLUDED.gender_scale,
                age_scale = EXCLUDED.age_scale,
                gender_pv = EXCLUDED.gender_pv,
                age_pv = EXCLUDED.age_pv,
                persona_index = EXCLUDED.persona_index,
                collected_at = now()
            """,
            (
                meta_id, period, gender, age, gender_ratio, age_ratio,
                gender_scale, age_scale, gender_pv, age_pv, persona_index,
            ),
        )
        conn.commit()
    finally:
        conn.close()
