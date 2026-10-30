"""여러 문서에 똑같이 들어 있는 청크를 찾아 보고한다 (읽기 전용).

검색은 **청크 최대 유사도**로 문서 점수를 정한다. 그래서 질의와 무관하게
중간 정도 점수를 내는 청크 하나가 문서 전체를 상위로 끌어올린다. 여러 문서에
공통으로 들어간 청크가 정확히 그런 역할을 한다.

2026-10-30에 실제로 관측했다 — 모든 기사에 붙는 저작권 고지가 어떤 질의에도
0.8547을 찍어 `"전기차 보조금"` 상위가 전부 무관한 기사로 채워졌다.

`chunker._BOILERPLATE`가 정형 문구를 거르지만 패턴 목록이라 한계가 있다.
채널 설명란의 주소·인사말처럼 매체마다 다른 문구는 잡히지 않는다.
이 스크립트로 주기적으로 확인하고, 필요하면 패턴을 늘린다.

실행 방법:
    python scripts/report_duplicate_chunks.py
    python scripts/report_duplicate_chunks.py --min-docs 30 --top 20
"""

import argparse

from src.database.db import get_conn

TABLES = ("dcat_dataset_vec", "meta_video_vec", "meta_news_vec", "meta_blog_vec")
KEY = {"dcat_dataset_vec": "dataset_id"}  # 그 외는 meta_id


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-docs", type=int, default=10,
                    help="이 수 이상의 문서에 나타나면 보고 (기본 10)")
    ap.add_argument("--top", type=int, default=8, help="테이블별 출력 개수 (기본 8)")
    args = ap.parse_args()

    conn = get_conn()
    cur = conn.cursor()
    for t in TABLES:
        key = KEY.get(t, "meta_id")
        cur.execute(f"SELECT count(*) FROM {t}")
        total = cur.fetchone()[0]
        if not total:
            print(f"\n[{t}] 비어 있음")
            continue
        cur.execute(
            f"""SELECT left(embed_text, 60), count(DISTINCT {key}) AS docs, count(*) AS rows
                FROM   {t}
                GROUP  BY embed_text
                HAVING count(DISTINCT {key}) >= %s
                ORDER  BY docs DESC
                LIMIT  %s""",
            (args.min_docs, args.top),
        )
        rows = cur.fetchall()
        print(f"\n[{t}] 전체 {total:,}청크 — {args.min_docs}개 이상 문서에 중복: {len(rows)}종 (상위 {args.top})")
        if not rows:
            print("    없음")
        for text, docs, cnt in rows:
            print(f"    {docs:>5,}개 문서 / {cnt:>5,}청크   {text}")
    cur.close()


if __name__ == "__main__":
    main()
