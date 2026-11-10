"""로컬 데이터베이스에 스키마를 만든다 — `docker compose up -d` 다음에 한 번 실행한다.

    python scripts/init_schema.py

- 접속 정보는 .env(DB_HOST·DB_PORT·DB_NAME·DB_USER·DB_PASSWORD)를 쓴다. psql이 없어도 된다.
- sql/*.sql을 **외래키 의존 순서**(scripts/validate_ddl.py의 ORDER)대로 적용하고,
  이어서 seeds.sql(표준값)과 views.sql을 적용한다. 알파벳 순으로 돌리면 부모 테이블보다
  자식 테이블이 먼저 와서 실패한다.
- 이미 스키마가 있으면(dcat_dataset 존재) 아무것도 하지 않는다 — 기존 데이터를 지우지 않는다.
"""
import re
import sys

from validate_ddl import ORDER  # 같은 scripts 폴더 — FK 의존 순서의 단일 출처
from src.database.db import get_conn

DROP_RE = re.compile(r"^\s*DROP\s+TABLE[^;]*;", re.IGNORECASE | re.MULTILINE)


def main() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.dcat_dataset')")
    if cur.fetchone()[0]:
        print("스키마가 이미 있습니다. 아무것도 바꾸지 않았습니다.")
        return 0
    files = [*ORDER, "seeds", "views"]
    for i, name in enumerate(files, 1):
        sql = DROP_RE.sub("", open(f"sql/{name}.sql", encoding="utf-8").read())
        try:
            cur.execute(sql)
            conn.commit()                      # 파일 단위로 확정한다(연결은 자동 커밋이 아니다)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            print(f"[{i:2d}/{len(files)}] {name:<32} 실패: {str(exc).strip().splitlines()[0]}")
            return 1
        print(f"[{i:2d}/{len(files)}] {name:<32} 완료")
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    print(f"\n스키마를 만들었습니다 — 테이블·뷰 {cur.fetchone()[0]}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
