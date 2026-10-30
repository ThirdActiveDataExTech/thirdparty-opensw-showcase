"""B2(관계 분석)·P0 착수 전 실현 가능성 실측 — 읽기 전용 진단.

NEXT_STEPS.md §8.1 P0-5 / development/04_Implementation_Methods.md §1.5 대응.
SELECT만 수행하며 어떤 쓰기도 하지 않는다. 출력은 집계 수치만(원본 레코드 미출력).

사용법:
    PYTHONPATH=. python scripts/diagnose_readiness.py
"""

import sys
from itertools import combinations

from src.database.db import get_conn

# active_meta_* → (상위 meta 테이블, 날짜 컬럼)
ACTIVE_SOURCES = {
    "active_meta_shopping_insight": ("meta_shopping_insight", "period"),
    "active_meta_persona_insight": ("meta_persona_insight", "period"),
    "active_meta_video": ("meta_video", "collected_at"),
    "active_meta_news": ("meta_news", "collected_at"),
    "active_meta_blog": ("meta_blog", "collected_at"),
}

# 본문/자막 확보율 점검 대상 — (테이블, 플래그 컬럼, 본문 컬럼)
CONTENT_SOURCES = [
    ("meta_news", "has_content", "content"),
    ("meta_blog", "has_content", "content"),
    ("meta_video", "has_transcript", "description"),
]

MIN_OVERLAP_DAYS = 30  # 시계열 상관 산출 최소 겹침 (04_Implementation_Methods.md §3 B2)


def h(title):
    print(f"\n## {title}\n")


def table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        print("| " + " | ".join("—" if v is None else str(v) for v in r) + " |")


def q1_metadata_quality(cur):
    h("Q1. 메타데이터 품질 — keyword_overlap 엣지 실현 가능성")

    cur.execute("""
        SELECT source_type,
               count(*),
               count(*) FILTER (WHERE keywords IS NULL
                                   OR jsonb_typeof(keywords) <> 'array'
                                   OR jsonb_array_length(keywords) = 0),
               round(avg(CASE WHEN jsonb_typeof(keywords)='array'
                              THEN jsonb_array_length(keywords) END), 1),
               count(*) FILTER (WHERE subjects IS NULL),
               min(length(description)),
               round(avg(length(description))),
               max(length(description)),
               count(*) FILTER (WHERE length(description) < 50)
          FROM dcat_dataset
         GROUP BY source_type ORDER BY source_type
    """)
    table(["source_type", "건수", "keywords 비어있음", "평균 키워드 수",
           "subjects NULL", "desc 최소", "desc 평균", "desc 최대", "desc<50자"],
          cur.fetchall())

    # 키워드 겹침 쌍 — 18개 수준이므로 파이썬에서 전수 비교
    cur.execute("""
        SELECT dataset_id, source_type,
               CASE WHEN jsonb_typeof(keywords)='array'
                    THEN ARRAY(SELECT jsonb_array_elements_text(keywords))
                    ELSE ARRAY[]::text[] END
          FROM dcat_dataset
    """)
    rows = cur.fetchall()
    sets = {d: (st, set(k)) for d, st, k in rows}

    pairs = list(combinations(sets, 2))
    overlap = [(a, b, len(sets[a][1] & sets[b][1])) for a, b in pairs]
    nonzero = [x for x in overlap if x[2] > 0]

    print(f"\n- 데이터셋 **{len(sets)}개** → 쌍 **{len(pairs)}개**")
    print(f"- 키워드가 **1개 이상 겹치는 쌍: {len(nonzero)}개** "
          f"({len(nonzero) / len(pairs) * 100:.1f}%)")
    if nonzero:
        top = sorted(nonzero, key=lambda x: -x[2])[:5]
        print(f"- 최다 겹침 상위: " + ", ".join(f"{c}개" for _, _, c in top))
        # 자카드 0.2 이상 (04 문서 §3 B2 임계값)
        jac = [(a, b, len(sets[a][1] & sets[b][1]) / len(sets[a][1] | sets[b][1]))
               for a, b, c in nonzero if sets[a][1] | sets[b][1]]
        strong = [x for x in jac if x[2] >= 0.2]
        print(f"- **자카드 ≥ 0.2 쌍: {len(strong)}개** ← 이 값이 곧 산출될 엣지 수")


def q2_temporal_overlap(cur):
    h("Q2. 시계열 기간 겹침 — temporal_comovement 엣지 실현 가능성")

    coverage, datasets_dates = [], {}
    for act, (meta, datecol) in ACTIVE_SOURCES.items():
        cast = "::date" if datecol == "collected_at" else ""
        cur.execute(f"""
            SELECT m.dataset_id, count(DISTINCT a.{datecol}{cast}),
                   min(a.{datecol}{cast}), max(a.{datecol}{cast}), count(*)
              FROM {act} a JOIN {meta} m ON m.id = a.meta_id
             GROUP BY m.dataset_id ORDER BY 2 DESC
        """)
        for ds, ndays, dmin, dmax, nrows in cur.fetchall():
            coverage.append((act.replace("active_meta_", ""), ds, ndays, dmin, dmax, nrows))
            cur.execute(f"""
                SELECT DISTINCT a.{datecol}{cast}
                  FROM {act} a JOIN {meta} m ON m.id = a.meta_id
                 WHERE m.dataset_id = %s
            """, (ds,))
            datasets_dates[ds] = {r[0] for r in cur.fetchall()}

    table(["소스", "dataset_id", "고유 날짜 수", "시작", "종료", "행 수"], coverage)

    pairs = list(combinations(datasets_dates, 2))
    ov = [(a, b, len(datasets_dates[a] & datasets_dates[b])) for a, b in pairs]
    usable = [x for x in ov if x[2] >= MIN_OVERLAP_DAYS]
    print(f"\n- 시계열 보유 데이터셋 **{len(datasets_dates)}개** → 쌍 **{len(pairs)}개**")
    print(f"- 겹치는 날짜 **{MIN_OVERLAP_DAYS}일 이상인 쌍: {len(usable)}개** "
          f"← 이 값이 곧 산출 가능한 상관 엣지 수")
    if ov:
        print(f"- 최대 겹침: {max(x[2] for x in ov)}일")


def q3_content(cur):
    h("Q3. 본문·자막 확보율 — P0-1 임베딩 절단 / P0-2 자막 활용의 정량 근거")

    rows = []
    for tbl, flag, textcol in CONTENT_SOURCES:
        cur.execute(f"""
            SELECT count(*), count(*) FILTER (WHERE {flag}),
                   percentile_cont(0.25) WITHIN GROUP (ORDER BY length({textcol})),
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY length({textcol})),
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY length({textcol})),
                   max(length({textcol})),
                   count(*) FILTER (WHERE length({textcol}) > 300)
              FROM {tbl} WHERE {textcol} IS NOT NULL
        """)
        n, ok, p25, p50, p75, mx, over = cur.fetchone()
        rate = f"{ok / n * 100:.1f}%" if n else "—"
        pct = f"{over / n * 100:.1f}%" if n else "—"
        rows.append((f"{tbl}.{textcol}", n, rate,
                     int(p25 or 0), int(p50 or 0), int(p75 or 0), mx, pct))
    table(["대상", "행 수", f"플래그 TRUE", "p25", "중앙값", "p75", "최대", "300자 초과 비율"], rows)
    print("\n> 임베딩 모델 `max_seq_length=128` → 한국어 약 200~300자에서 절단된다.")
    print("> **300자 초과 비율**이 곧 '본문 일부가 버려지고 있는 레코드'의 비율이다.")


def q4_schema_drift(cur):
    h("Q4. 저장소 DDL ↔ 실제 DB 불일치")

    cur.execute("""
        SELECT table_name, (SELECT count(*) FROM information_schema.columns c
                             WHERE c.table_name = t.table_name)
          FROM information_schema.tables t
         WHERE table_schema='public'
           AND (table_name LIKE 'dcat%' OR table_name LIKE 'meta%'
                OR table_name LIKE 'active%' OR table_name LIKE 'data%')
         ORDER BY 1
    """)
    import os
    sqldir = os.path.join(os.path.dirname(__file__), "..", "sql")
    ddl = " ".join(open(os.path.join(sqldir, f), encoding="utf-8").read()
                   for f in os.listdir(sqldir) if f.endswith(".sql"))
    rows = []
    for name, ncol in cur.fetchall():
        has = f"CREATE TABLE {name}" in ddl or f"CREATE TABLE IF NOT EXISTS {name}" in ddl
        cur.execute(f"SELECT count(*) FROM {name}")
        rows.append((name, ncol, cur.fetchone()[0], "✅" if has else "❌ **없음**"))
    table(["테이블", "컬럼 수", "행 수", "sql/ DDL"], rows)


def main():
    conn = get_conn()
    conn.set_session(readonly=True)          # 쓰기 원천 차단
    try:
        cur = conn.cursor()
        print("# 착수 전 실현 가능성 진단 (읽기 전용)")
        q1_metadata_quality(cur)
        q2_temporal_overlap(cur)
        q3_content(cur)
        q4_schema_drift(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
