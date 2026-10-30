"""PostgreSQL 커넥션 — 프로세스당 1개 재사용 (성능 개선, 2026-07-28).

기존엔 호출부(`database/*.py`, 파이프라인)가 함수 호출마다 `get_conn()`으로 새
커넥션을 열고 즉시 닫아서, 원격 DB(TCP+인증 왕복)에 쿼리 수만큼 반복 접속하는
비용이 컸다(예: YouTube 1400개+ 채널 재실행 ~5분). 이제 프로세스당 커넥션 1개를
지연 생성해 재사용한다.

- `get_conn()` 호출마다 가볍게 살아있는지 확인(`SELECT 1`) 후, 죽어있으면
  재연결한다 — STT 처리처럼 쿼리 사이 유휴 시간이 길 때(수십 초~몇 분) 네트워크나
  DB 서버가 유휴 커넥션을 끊을 수 있어서 필요. `.closed` 속성만으로는 이런
  서버 쪽 끊김을 못 잡는다(로컬에서 직접 닫은 경우만 반영됨).
- 호출부 코드(`conn = get_conn(); ...; conn.close()`)는 전혀 안 바뀐다 — `close()`는
  실제로 커넥션을 닫지 않고, 트랜잭션이 남아있으면 rollback만 해서 다음 재사용을
  위해 정리한다.

⚠️ **멀티스레드 주의**: 이 모듈은 "한 프로세스 = 순차 실행"을 전제로 커넥션 1개를
공유한다. psycopg2 커넥션은 스레드 세이프하지 않다 — 나중에 Airflow가 같은 프로세스
안에서 여러 태스크를 스레드로 동시 실행하는 구조(예: 특정 LocalExecutor 설정)로
바뀌면 이 설계 그대로는 안 되고, 그 전에 반드시 `psycopg2.pool`(예:
`ThreadedConnectionPool`)로 마이그레이션해야 한다 — 인터페이스(`get_conn()`/
`close()`)는 그대로 유지한 채 이 파일 내부만 바꾸면 되도록 설계했으니 호출부
(`database/meta_*.py`, `pipelines/*.py`)는 그때도 안 건드려도 된다.
KubernetesExecutor(태스크마다 별도 Pod = 별도 프로세스)로 가면 이 문제 자체가
없다 — Airflow 실행 방식은 아직 미정(`NEXT_STEPS.md` §6.2).
"""

import psycopg2
import psycopg2.extensions
from src.common import config

_conn = None


class _ReusableConnection:
    """get_conn()이 반환하는 래퍼 — close()가 실제로 닫지 않고 트랜잭션만 정리한다."""

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def close(self):
        conn = object.__getattribute__(self, "_conn")
        try:
            if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                conn.rollback()
        except Exception:
            pass


def _connect():
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def _is_alive(conn) -> bool:
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        return False


def get_conn():
    global _conn
    if _conn is None or _conn.closed or not _is_alive(_conn):
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
        _conn = _connect()
    return _ReusableConnection(_conn)
