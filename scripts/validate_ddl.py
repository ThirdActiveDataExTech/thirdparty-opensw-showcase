"""sql/*.sql 문법 검증 — 임시 스키마에 생성 후 전부 롤백한다.

안전장치:
  - DROP TABLE 구문을 실행 전에 제거한다.
    search_path에 public이 포함되므로(vector 타입 해석에 필요) DROP을 그대로 두면
    임시 스키마가 아니라 **실제 테이블**을 찾아 지운다. 트랜잭션이 롤백해도
    그때까지 ACCESS EXCLUSIVE 락이 잡히므로 아예 실행하지 않는다.
  - 전 과정을 단일 트랜잭션에서 수행하고 마지막에 무조건 ROLLBACK 한다.
  - 생성되는 것은 _ddlcheck 스키마 안의 사본뿐이다.

사용법: PYTHONPATH=. python scripts/validate_ddl.py
"""

import re
import sys

from src.database.db import get_conn

# FK 의존 순서 (부모 → 자식)
ORDER = [
    # 카탈로그·운영
    "dcat_dataset", "dcat_provenance", "data_registry", "dataset_credentials",
    "dcat_dataset_vec",
    # 표준값 레지스트리 (관계·지표가 FK로 참조하므로 선행)
    "metric_registry", "relation_type_registry",
    # 정형 계층 (협력기관 합의 스키마)
    "dcat_dataset_attr", "active_meta_dataset", "dcat_dataset_relation",
    "meta_datagokr_file", "active_meta_file", "meta_file_relation",
    "meta_datagokr_file_vec", "dcat_dataset_draft", "metadata_entry",
    # 비정형 계층 (source_type 기준 명명)
    "meta_video", "meta_video_vec", "active_meta_video",
    "meta_news", "meta_news_vec", "active_meta_news",
    "meta_blog", "meta_blog_vec", "active_meta_blog",
    "meta_shopping_insight", "active_meta_shopping_insight",
    "meta_persona_insight", "active_meta_persona_insight",
]

DROP_RE = re.compile(r"^\s*DROP\s+TABLE[^;]*;", re.IGNORECASE | re.MULTILINE)


def main() -> int:
    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    ok, fail = [], []
    try:
        cur.execute("CREATE SCHEMA _ddlcheck")
        cur.execute("SET LOCAL search_path = _ddlcheck, public")
        for name in ORDER:
            sql = DROP_RE.sub("", open(f"sql/{name}.sql", encoding="utf-8").read())
            try:
                cur.execute(sql)
                ok.append(name)
            except Exception as exc:  # noqa: BLE001 — 문법 오류를 모아서 보고한다
                fail.append((name, str(exc).strip().splitlines()[0]))
                conn.rollback()
                cur = conn.cursor()
                cur.execute("CREATE SCHEMA IF NOT EXISTS _ddlcheck")
                cur.execute("SET LOCAL search_path = _ddlcheck, public")
    finally:
        conn.rollback()
        conn.close()

    print(f"문법 통과 {len(ok)}/{len(ORDER)}")
    for n in ok:
        print("  ✅", n)
    for n, e in fail:
        print("  ❌", n, "→", e)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
