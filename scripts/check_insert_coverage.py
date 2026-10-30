"""INSERT 구문이 NOT NULL 컬럼을 전부 채우는지 검사한다 (읽기 전용).

배경: 2026-10-27 dcat_dataset.source를 NOT NULL(기본값 없음)로 추가했는데
register_dataset.py의 INSERT가 이 컬럼을 빠뜨려 신규 등록이 전부 실패했다.
컬럼을 추가할 때마다 INSERT 경로를 전수로 다시 보기 위한 도구다.

사용법: PYTHONPATH=. python scripts/check_insert_coverage.py
종료코드 1 = 누락 있음
"""

import glob
import re
import sys
from collections import defaultdict

from src.database.db import get_conn

# INSERT INTO <table> ( ... )  — 테이블명이 식별자인 경우만 정적으로 판정한다
INSERT_RE = re.compile(
    r'INSERT\s+INTO\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)', re.IGNORECASE | re.DOTALL)
# 테이블명이 변수/포맷 문자열인 경우 — 자동 판정 불가
DYNAMIC_RE = re.compile(r'INSERT\s+INTO\s+[\{"\']', re.IGNORECASE)


def required_columns():
    conn = get_conn()
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, column_name FROM information_schema.columns
         WHERE table_schema='public' AND is_nullable='NO' AND column_default IS NULL
         ORDER BY table_name, ordinal_position""")
    req = defaultdict(set)
    for t, c in cur.fetchall():
        req[t].add(c)
    conn.close()
    return req


def main() -> int:
    req = required_columns()
    files = sorted(glob.glob("src/**/*.py", recursive=True)
                   + glob.glob("scripts/*.py") + glob.glob("sql/*.sql"))
    problems, dynamic, checked = [], [], 0

    for path in files:
        if path.endswith("check_insert_coverage.py"):
            continue
        text = open(path, encoding="utf-8").read()
        # SQL 주석 제거 (INSERT 예시가 주석에 있는 경우 오탐 방지)
        text = re.sub(r'^\s*--.*$', '', text, flags=re.MULTILINE)

        for m in DYNAMIC_RE.finditer(text):
            line = text[:m.start()].count("\n") + 1
            dynamic.append(f"{path}:{line}")

        for m in INSERT_RE.finditer(text):
            table = m.group(1)
            if table not in req:
                continue
            cols = {c.strip() for c in m.group(2).replace("\n", " ").split(",") if c.strip()}
            checked += 1
            missing = req[table] - cols
            if missing:
                line = text[:m.start()].count("\n") + 1
                problems.append((f"{path}:{line}", table, sorted(missing)))

    print(f"검사한 INSERT: {checked}건 (정적 테이블명 기준)\n")
    if problems:
        print("❌ NOT NULL 컬럼 누락")
        for loc, t, miss in problems:
            print(f"   {loc}\n      {t} ← {', '.join(miss)}")
    else:
        print("✅ 누락 없음")

    if dynamic:
        print(f"\n⚠️ 테이블명이 동적이라 자동 판정 불가 — 수동 확인 필요 ({len(dynamic)}건)")
        for d in sorted(set(dynamic)):
            print(f"   {d}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
