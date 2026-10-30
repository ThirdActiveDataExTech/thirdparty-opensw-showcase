"""자연어 질의로 수집·임베딩된 비정형 데이터를 검색한다.

실행 방법:
    python scripts/search_demo.py "위암 조기 진단"
    python scripts/search_demo.py "HBM 고대역폭 메모리" --source video --top 5

동작 방식은 두 가지가 핵심이다.

1. **질의 프리픽스** — 모델(multilingual-e5-base)은 문서에 `passage: `,
   질의에 `query: `를 붙여 학습됐다. 빠뜨려도 오류가 나지 않고 검색 품질만
   조용히 떨어진다(docs/adr/016_Embedding_Model_And_Conventions.md).

2. **청크 최대 유사도 집계** — 문서 1건은 여러 청크로 나뉘어 저장된다.
   점수는 평균이 아니라 **최대값**을 쓴다. 긴 문서에서 질의와 맞는 청크가
   하나이고 무관한 청크가 여럿일 때, 평균은 정답 신호를 희석시킨다.
"""

import argparse

from src.database.db import get_conn
from src.embedding import embedder

# (벡터 테이블, 원본 테이블, 조인 키, 표시할 컬럼)
SOURCES = {
    "video": ("meta_video_vec", "meta_video", "id", "title", "channel_title"),
    "news":  ("meta_news_vec",  "meta_news",  "id", "title", "publisher"),
    "blog":  ("meta_blog_vec",  "meta_blog",  "id", "title", "blogger_name"),
}


def search(query: str, source: str, top_k: int):
    vec, base, key, title_col, sub_col = SOURCES[source]
    q = str(embedder.encode_query(query))          # ← `query: ` 프리픽스가 여기서 붙는다

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT b.{title_col}, b.{sub_col},
               ROUND(MAX(1 - (v.embedding <=> %s::vector))::numeric, 4) AS score
        FROM   {vec} v
        JOIN   {base} b ON b.{key} = v.meta_id
        GROUP  BY b.{key}, b.{title_col}, b.{sub_col}   -- 청크를 원본 1건으로 묶는다
        ORDER  BY score DESC
        LIMIT  %s
        """,
        (q, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help="검색할 자연어 질의")
    ap.add_argument("--source", choices=sorted(SOURCES), default="video")
    ap.add_argument("--top", type=int, default=5, help="결과 개수 (기본 5)")
    args = ap.parse_args()

    print(f'\n[{args.source}] "{args.query}"\n')
    rows = search(args.query, args.source, args.top)
    if not rows:
        print("  결과 없음 — 데이터를 수집하고 임베딩했는지 확인하세요.")
        return
    for i, (title, sub, score) in enumerate(rows, 1):
        print(f"  {i}. {score}  {title}")
        print(f"            {sub}")
    print()


if __name__ == "__main__":
    main()
