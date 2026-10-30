"""dcat_dataset.theme — 원천 분류 원문을 수집 결과에서 집계한다.

`theme`은 **원천이 붙인 분류를 그대로 담는 컬럼**이다(협력기관 합의).
`category`(디지털 집현전 공통 분류)와는 별개 컬럼이다.

소스마다 원천이 주는 것이 다르다 (2026-10-29 실측).

| 소스 | 원천 분류 | 비고 |
|---|---|---|
| video | `categoryId`(YouTube 고정 32종) + `topicCategories`(위키 주제) | 100% / 97% 수집 중 |
| shopping·persona | 네이버 쇼핑 카테고리 `cat_level1` | 100% |
| news·blog | **없음** | 네이버 검색 API가 분류를 주지 않는다 |

뉴스·블로그는 네이버 호스팅 기사 한정으로 페이지 섹션을 스크래핑하면 얻을 수
있지만 외부 기사가 약 68%라 커버가 안 된다. 분류 모델로 채우는 것이 현실적인
대안이고(ADR-013 임베딩 zero-shot), 그때까지는 비워 둔다 — **없는 분류를
지어내지 않는다.**
"""

import json
import logging
from typing import List

from src.common.youtube_categories import name_of, topic_name
from src.database.db import get_conn

logger = logging.getLogger(__name__)

# 한 데이터셋의 theme에 담을 상위 N개. 꼬리가 길면 주제가 흐려진다.
TOP_N = 8


def _collect_video(cur, dataset_id: str) -> List[str]:
    """영상 카테고리 + 위키 주제를 빈도순으로."""
    cur.execute(
        """SELECT category_id, count(*) FROM meta_video
            WHERE dataset_id = %s AND category_id IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC""",
        (dataset_id,),
    )
    themes = [name_of(cid) for cid, _ in cur.fetchall()]

    cur.execute(
        """SELECT t.value, count(*) FROM meta_video m,
                  jsonb_array_elements_text(m.topic_categories) AS t(value)
            WHERE m.dataset_id = %s
            GROUP BY 1 ORDER BY 2 DESC""",
        (dataset_id,),
    )
    for url, _ in cur.fetchall():
        name = topic_name(url)
        if name and name not in themes:
            themes.append(name)
    return themes


def _collect_category(cur, dataset_id: str, table: str) -> List[str]:
    """선언형: 네이버 쇼핑 카테고리 대분류."""
    cur.execute(
        f"""SELECT DISTINCT cat_level1 FROM {table}
             WHERE dataset_id = %s AND cat_level1 IS NOT NULL
             ORDER BY 1""",
        (dataset_id,),
    )
    return [r[0] for r in cur.fetchall()]


def sync_theme(dataset_id: str, source_type: str) -> List[str]:
    """수집 결과에서 theme을 다시 집계해 dcat_dataset에 반영한다.

    news·blog는 원천 분류가 없어 아무것도 하지 않는다(빈 배열을 덮어쓰지도 않는다).
    반환값은 실제로 저장한 theme 목록.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        if source_type == "video":
            themes = _collect_video(cur, dataset_id)
        elif source_type == "shopping_insight":
            themes = _collect_category(cur, dataset_id, "meta_shopping_insight")
        elif source_type == "persona_insight":
            themes = _collect_category(cur, dataset_id, "meta_persona_insight")
        else:
            return []

        themes = themes[:TOP_N]
        if not themes:
            return []
        cur.execute(
            "UPDATE dcat_dataset SET theme = %s, updated_at = now() WHERE dataset_id = %s",
            (json.dumps(themes, ensure_ascii=False), dataset_id),
        )
        conn.commit()
        return themes
    finally:
        conn.close()
