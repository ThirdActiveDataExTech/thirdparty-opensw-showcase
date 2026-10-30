"""dcat_dataset.category — 공통 분류 자동 부여 (임베딩 zero-shot).

협력기관은 정형에 **언어 모델**로 부여하고, 응답이 없거나 표 밖의 값만 나오면
**데이터셋 요약 임베딩과 가장 가까운 중분류 1개**를 넣는다고 정의했다.

우리는 [ADR-013](../../docs/adr/013_No_External_LLM_API.md)으로 외부 LLM을 쓰지
않으므로 **그 폴백 경로를 주 경로로 쓴다.** 같은 분류표·같은 형식·같은 개수 규칙을
지키므로 결과는 상호 운용된다.

방식:
  1. 분류표 76개를 각각 임베딩한다(한 번 계산 후 프로세스 내 재사용)
  2. 데이터셋 텍스트(제목 + 설명 + 키워드 + theme)를 임베딩한다
  3. 코사인 유사도 상위 N개를 고른다. 단 **임계값 미만은 버린다** —
     억지로 3개를 채우면 관련 없는 분류가 붙는다

⚠️ 분류 품질은 임베딩 모델 성능에 직접 묶인다. 현재 모델
(`paraphrase-multilingual-mpnet-base-v2`)은 검색용으로 학습된 것이 아니라
짧은 라벨 ↔ 짧은 텍스트 비교에는 그나마 맞지만, 전환을 검토 중인
`multilingual-e5-base`로 바꾸면 **분류 결과가 달라진다. 모델 교체 시 재부여가 필요하다.**
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.common import config
from src.common.category_taxonomy import ALL_CATEGORIES, MAX_PER_DATASET, validate
from src.database.db import get_conn
from src.embedding import embedder

logger = logging.getLogger(__name__)

# 이 값 미만이면 분류를 붙이지 않는다.
#
# **0.0 = 사실상 항상 부여한다.** 2026-10-29 결정: 틀린 분류가 섞이더라도 일단
# 채워 두고, 로컬 sLLM(ADR-013 🟦 목표선)이 생기면 그쪽으로 대체한다. 분류가
# 비어 있으면 포털 전체 필터링이 아예 성립하지 않기 때문이다.
#
# ⚠️ **현재 분류 품질은 신뢰할 수 없다.** 사람이 본 정답과 비교한 실측:
#      현 모델 Top-1 3/8, e5-base Top-1 3/8 (모델 교체로 해결되지 않는다)
#      '패션의류 검색 트렌드' → '문화 > 공예', 'HBM 뉴스' → '문화 > 방송·미디어'
#    76개 라벨은 '의료 > 공중보건' 같은 짧은 명사구인데, 임베딩으로 긴 데이터셋
#    설명과 맞추는 일 자체가 이 모델들의 학습 목표가 아니다.
#
# e5 계열은 유사도가 0.7~1.0에 몰려 임계값으로 거르기도 어렵다 — 틀린 답에도
# 0.82~0.85가 나온다. 그래서 임계값 방식 자체를 포기하고 0으로 둔다.
MIN_SIMILARITY = float(config.get_env("CATEGORY_MIN_SIMILARITY", "0.0"))

_label_vecs: Optional[np.ndarray] = None


def _get_label_vectors() -> np.ndarray:
    """분류표 76개의 임베딩. 프로세스당 한 번만 계산한다."""
    global _label_vecs
    if _label_vecs is None:
        logger.info("분류표 임베딩 생성 (%d개)", len(ALL_CATEGORIES))
        _label_vecs = np.array(embedder.encode(ALL_CATEGORIES))
    return _label_vecs


def _dataset_text(row: Dict) -> str:
    """분류 판단에 쓸 데이터셋 요약 텍스트.

    theme(원천 분류)을 넣는 이유: 'Health', '패션의류' 같은 원천 분류가 공통 분류와
    어휘적으로 가까워 신호가 세다. 없으면 제목·설명·키워드만 쓴다.
    """
    parts = [row.get("title") or "", row.get("description") or ""]
    for col in ("keywords", "theme"):
        v = row.get(col) or []
        if isinstance(v, str):
            v = json.loads(v)
        if v:
            parts.append(", ".join(str(x) for x in v))
    return ". ".join(p for p in parts if p)


def classify(text: str, top_n: int = MAX_PER_DATASET) -> List[Tuple[str, float]]:
    """텍스트에 가장 가까운 분류를 (값, 유사도) 목록으로. 임계값 미만은 제외."""
    if not text.strip():
        return []
    labels = _get_label_vectors()
    # 데이터셋 텍스트를 '질의'로, 분류 라벨을 '문서'로 둔다 — 짧은 라벨에서
    # 긴 텍스트를 찾는 게 아니라 그 반대가 이 작업의 모양이다.
    v = np.array(embedder.encode_query(text))
    sims = labels @ v / (np.linalg.norm(labels, axis=1) * np.linalg.norm(v))
    order = np.argsort(-sims)[:top_n]
    return [(ALL_CATEGORIES[i], float(sims[i])) for i in order
            if sims[i] >= MIN_SIMILARITY]


def sync_category(dataset_id: str) -> List[str]:
    """데이터셋의 category를 다시 계산해 반영한다. 반환: 저장한 분류 목록.

    이미 값이 있어도 덮어쓴다 — 수집이 진행되면 theme과 item 구성이 바뀌어
    분류가 달라질 수 있다. 사람이 손으로 고친 값을 보존해야 할 필요가 생기면
    그때 '수동 지정' 플래그를 둔다.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT dataset_id, title, description, keywords, theme
                 FROM dcat_dataset WHERE dataset_id = %s""",
            (dataset_id,),
        )
        row = cur.fetchone()
        if row is None:
            return []
        names = [d[0] for d in cur.description]
        scored = classify(_dataset_text(dict(zip(names, row))))
        cats = validate([c for c, _ in scored])
        if not cats:
            logger.info("category 미부여 (텍스트 없음): %s", dataset_id)
            return []
        cur.execute(
            "UPDATE dcat_dataset SET category = %s, updated_at = now() WHERE dataset_id = %s",
            (json.dumps(cats, ensure_ascii=False), dataset_id),
        )
        conn.commit()
        return cats
    finally:
        conn.close()
