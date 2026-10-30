"""벡터 테이블 증분 동기화 — 원본 1건 = 청크 N건.

**전량 재생성하지 않는다.** 원본 텍스트에서 만든 청크 목록을 저장된 청크 목록과
비교해, 달라진 항목만 지우고 다시 넣는다. 비교는 DB에서 끝나므로 할 일이 없으면
모델을 올리지도 않는다.

청킹 이유는 src/embedding/chunker.py 참조. 요약하면 모델이 짧은 질의 ↔ 긴 문서
비대칭 비교에서 무너지기 때문이고, 검색은 **청크 최대 유사도**로 집계한다.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.database.db import get_conn
from src.embedding import chunker, embedder

logger = logging.getLogger(__name__)


def _text_dataset(row: Dict[str, Any]) -> str:
    """dcat_dataset: 제목 + 설명 + 키워드."""
    kws = row.get("keywords") or []
    if isinstance(kws, str):
        kws = json.loads(kws)
    kw = ", ".join(kws) if kws else ""
    parts = [row.get("title") or "", row.get("description") or ""]
    if kw:
        parts.append(f"키워드: {kw}")
    return ". ".join(p for p in parts if p)


def _text_video(row: Dict[str, Any]) -> str:
    """meta_video: 제목 + 설명 + 태그."""
    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = json.loads(tags)
    tag = ", ".join(tags) if tags else ""
    parts = [row.get("title") or "", row.get("description") or ""]
    if tag:
        parts.append(f"태그: {tag}")
    return ". ".join(p for p in parts if p)


def _text_article(row: Dict[str, Any]) -> str:
    """meta_news / meta_blog: 제목 + 요약 (+ 본문 앞 2000자).

    본문 스크래핑에 실패한 항목(has_content=FALSE)은 제목·요약만 쓴다.

    청킹 이전에는 500자로 잘랐다. 어차피 max_seq_length(128토큰)를 넘으면 버려져
    더 넣을 이유가 없었기 때문이다. 이제는 청크마다 따로 인코딩하므로 본문을 더
    담을수록 검색에 걸릴 구석이 늘어난다. 2000자면 청크 25개 안팎이다.
    """
    parts = [row.get("title") or "", row.get("description") or ""]
    if row.get("has_content"):
        parts.append((row.get("content") or "")[:2000])
    return ". ".join(p for p in parts if p)


# (원본 테이블, 벡터 테이블, 벡터쪽 키 컬럼, 원본쪽 키 컬럼, 조회 컬럼, 텍스트 생성 함수)
_SPECS: Dict[str, Tuple[str, str, str, str, str, Callable]] = {
    "dcat_dataset": ("dcat_dataset", "dcat_dataset_vec", "dataset_id", "dataset_id",
                     "dataset_id, title, description, keywords", _text_dataset),
    "meta_video":   ("meta_video", "meta_video_vec", "meta_id", "id",
                     "id, title, description, tags", _text_video),
    "meta_news":    ("meta_news", "meta_news_vec", "meta_id", "id",
                     "id, title, description, content, has_content", _text_article),
    "meta_blog":    ("meta_blog", "meta_blog_vec", "meta_id", "id",
                     "id, title, description, content, has_content", _text_article),
}


def sync(spec_name: str, dataset_id: Optional[str] = None,
         limit: Optional[int] = None) -> Dict[str, int]:
    """벡터 테이블을 원본과 맞춘다.

    반환: {'checked': 검사한 원본 수, 'items': 다시 만든 원본 수,
           'chunks': 생성한 청크 수, 'skipped': 변경 없던 원본 수}

    dataset_id를 주면 그 데이터셋 소속만 처리한다(수집 파이프라인용).
    limit은 한 번에 처리할 최대 **원본 건수** — 큰 작업을 나눠 돌릴 때 쓴다.
    """
    base, vec, vkey, skey, cols, build = _SPECS[spec_name]
    conn = get_conn()
    try:
        cur = conn.cursor()
        where, params = "", []
        if dataset_id is not None:
            where = " WHERE b.dataset_id = %s"
            params.append(dataset_id)

        # 원본 + 저장된 청크 목록(순서대로)을 한 번에 읽는다
        select_cols = ", ".join("b." + c.strip() for c in cols.split(","))
        cur.execute(
            f"SELECT {select_cols}, v.stored "
            f"FROM {base} b "
            f"LEFT JOIN (SELECT {vkey} AS k, "
            f"                  array_agg(embed_text ORDER BY chunk_index) AS stored "
            f"             FROM {vec} GROUP BY {vkey}) v ON v.k = b.{skey}"
            f"{where}",
            params,
        )
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]

        todo: List[Tuple[Any, List[str]]] = []
        skipped = 0
        for r in rows:
            new_chunks = chunker.chunk(build(r))
            if not new_chunks:
                skipped += 1
                continue
            if (r.get("stored") or []) == new_chunks:
                skipped += 1
                continue
            todo.append((r[skey], new_chunks))

        checked = len(rows)
        if not todo:
            logger.info("%s 임베딩: 변경 없음 (검사 %d건)", spec_name, checked)
            return {"checked": checked, "items": 0, "chunks": 0, "skipped": skipped}

        pending = len(todo)
        if limit is not None and pending > limit:
            todo = todo[:limit]

        # 청크를 전부 모아 한 번에 인코딩한다 — 배치가 클수록 빠르다
        flat: List[str] = []
        spans: List[Tuple[Any, int, int]] = []
        for pk, chs in todo:
            spans.append((pk, len(flat), len(flat) + len(chs)))
            flat.extend(chs)
        logger.info("%s 임베딩: 원본 %d건 중 %d건 처리 (청크 %d개)",
                    spec_name, pending, len(todo), len(flat))

        vectors = embedder.encode(flat)

        for pk, lo, hi in spans:
            # 청크 수가 줄어들 수 있으므로 지우고 다시 넣는다
            cur.execute(f"DELETE FROM {vec} WHERE {vkey} = %s", (pk,))
            for idx, i in enumerate(range(lo, hi)):
                cur.execute(
                    f"INSERT INTO {vec} ({vkey}, chunk_index, embedding, embed_text, model_name) "
                    f"VALUES (%s, %s, %s::vector, %s, %s)",
                    (pk, idx, str(vectors[i]), flat[i], embedder.MODEL_NAME),
                )
        conn.commit()
        return {"checked": checked, "items": len(todo),
                "chunks": len(flat), "skipped": skipped}
    finally:
        conn.close()


def sync_for_dataset(source_type: str, dataset_id: str,
                     limit: Optional[int] = None) -> Dict[str, int]:
    """수집 파이프라인이 부르는 진입점. 데이터셋 카탈로그 + 아이템 벡터를 맞춘다.

    shopping_insight·persona_insight는 아이템이 카테고리라 본문이 없다 —
    데이터셋 단위 임베딩만 한다.
    """
    result = sync("dcat_dataset", dataset_id=dataset_id)
    item_spec = {"video": "meta_video", "news": "meta_news",
                 "blog": "meta_blog"}.get(source_type)
    if item_spec:
        item = sync(item_spec, dataset_id=dataset_id, limit=limit)
        for k in result:
            result[k] += item[k]
    return result
