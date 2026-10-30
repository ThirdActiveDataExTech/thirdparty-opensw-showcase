"""소스별로 무엇이 얼마나 수집되었는지 보여준다 (읽기 전용).

수집 파이프라인이 실제로 무엇을 가져오는지 확인하는 용도다. 원천마다
수집 단위와 저장되는 항목이 다르므로, 건수와 함께 실제 행을 몇 개 보여준다.

실행 방법:
    python scripts/show_collected.py
    python scripts/show_collected.py --samples 5
"""

import argparse
import unicodedata

from src.database.db import get_conn


def _w(text: str) -> int:
    """터미널에서 차지하는 칸 수. 한글·한자는 두 칸을 쓴다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    """표시 폭 기준으로 오른쪽을 채운다. 넘치면 잘라낸다."""
    out = ""
    for c in text:
        if _w(out) + _w(c) > width - 1:
            return out + "… " + " " * max(0, width - _w(out) - 2)
        out += c
    return out + " " * (width - _w(out))

COUNTS = [
    ("YouTube 영상",      "SELECT count(*) FROM meta_video"),
    ("  └ 자막 생성됨",    "SELECT count(*) FROM meta_video WHERE has_transcript"),
    ("네이버 뉴스 기사",    "SELECT count(*) FROM meta_news"),
    ("  └ 본문 수집됨",    "SELECT count(*) FROM meta_news WHERE has_content"),
    ("네이버 블로그 포스트", "SELECT count(*) FROM meta_blog"),
    ("  └ 본문 수집됨",    "SELECT count(*) FROM meta_blog WHERE has_content"),
    ("쇼핑인사이트 카테고리", "SELECT count(*) FROM meta_shopping_insight"),
    ("  └ 시계열 관측",    "SELECT count(*) FROM active_meta_shopping_insight"),
    ("페르소나 카테고리",   "SELECT count(*) FROM meta_persona_insight"),
    ("  └ 시계열 관측",    "SELECT count(*) FROM active_meta_persona_insight"),
]

SAMPLES = [
    ("YouTube — 영상 메타데이터", """
        SELECT left(title, 42), channel_title, duration_seconds || '초',
               to_char(initial_view_count, 'FM999,999,999') || '회'
        FROM meta_video WHERE initial_view_count IS NOT NULL
        ORDER BY initial_view_count DESC LIMIT %s"""),
    ("네이버 뉴스 — 기사 메타데이터", """
        SELECT left(title, 42), publisher, to_char(published_at, 'YYYY-MM-DD'),
               length(content) || '자'
        FROM meta_news WHERE has_content ORDER BY published_at DESC LIMIT %s"""),
    ("네이버 블로그 — 포스트 메타데이터", """
        SELECT left(title, 42), blogger_name, to_char(published_at, 'YYYY-MM-DD'),
               length(content) || '자'
        FROM meta_blog WHERE has_content ORDER BY published_at DESC LIMIT %s"""),
    ("쇼핑인사이트 — 검색량 시계열", """
        SELECT m.category_name, a.period::text, a.gender || '/' || a.age,
               round(a.normalized_ratio::numeric, 2)::text
        FROM active_meta_shopping_insight a JOIN meta_shopping_insight m ON m.id = a.meta_id
        ORDER BY a.period DESC, a.id LIMIT %s"""),
    ("페르소나 — 성별·연령 분포", """
        SELECT m.category_name, a.period::text, a.gender || '/' || a.age,
               round(a.persona_index::numeric, 2)::text
        FROM active_meta_persona_insight a JOIN meta_persona_insight m ON m.id = a.meta_id
        ORDER BY a.period DESC, a.id LIMIT %s"""),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=3, help="원천별 표본 행 수 (기본 3)")
    args = ap.parse_args()

    conn = get_conn()
    cur = conn.cursor()

    print("\n수집 현황")
    print("─" * 62)
    for label, q in COUNTS:
        cur.execute(q)
        print(f"  {_pad(label, 30)}{cur.fetchone()[0]:>10,}")

    for title, q in SAMPLES:
        cur.execute(q, (args.samples,))
        rows = cur.fetchall()
        print(f"\n{title}")
        print("─" * 62)
        for r in rows:
            cells = [str(c) if c is not None else "-" for c in r]
            print("  " + _pad(cells[0], 48) + _pad(cells[1], 24) + _pad(cells[2], 14) + cells[3])
    print()
    cur.close()


if __name__ == "__main__":
    main()
