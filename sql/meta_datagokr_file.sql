-- ═══════════════════════════════════════════════════════════════
-- meta_datagokr_file : 데이터파일 현황 메타데이터 (파일 1건 = 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 정형(엑셀/CSV 등 파일) 데이터의 파일 단위 정보 + 항목별 기술통계량.
-- v0.1 OpenSearch datasets 인덱스를 흡수한 테이블이다.
--
-- 출처 통합: 협력기관 DDL과 통합한 정본. 원본은 협력기관 수신본  참조.
--
-- 비정형과의 대응: 비정형의 아이템 계층(meta_video, meta_news 등)에
-- 해당하는 자리이나, 테이블은 공유하지 않고 정형 전용으로 둔다.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_datagokr_file CASCADE;

CREATE TABLE meta_datagokr_file (

    -- ── 식별 ──────────────────────────────────────────────────
    file_id         TEXT PRIMARY KEY,
    -- 데이터파일 식별자 | 내용 해시 기반
    -- 포털 cetus_dataset_file.rawdata_id와 동일 값

    dataset_id      TEXT NOT NULL
                    REFERENCES dcat_dataset(dataset_id)
                    ON UPDATE CASCADE ON DELETE CASCADE,
    -- 데이터셋 식별자 | dcat_dataset 참조

    file_name       TEXT NOT NULL,
    -- 파일데이터명 | 접미 날짜가 수록 시점을 나타낸다
    -- [협력기관] 관계 서비스 API의 table_name. 관계 서비스는 이 값을 키로
    --            조회·대체 등록한다 (그래서 UNIQUE 인덱스가 걸려 있다)

    display_name    TEXT,
    -- 표시명 | LLM 생성 한국어 표시명. 비면 file_name을 사용한다

    -- ── 파일 속성 ─────────────────────────────────────────────
    file_format     TEXT,
    -- 확장자 | [협력기관] CSV / XLSX / JSON / API / KOSIS

    byte_size       BIGINT,
    -- 파일 크기 | 바이트

    content_sha256  TEXT NOT NULL UNIQUE,
    -- 내용 해시 | 중복 등록 판별
    -- [협력기관] 메타데이터만 있는 경우에는 구조 해시를 쓴다

    storage_key     TEXT,
    -- 보관 경로 | SeaweedFS S3 키
    -- 경로 규약은 architecture/06_Object_Storage_Format_Spec.md 참조

    -- ── 구조·통계 ─────────────────────────────────────────────
    record_count    BIGINT,
    -- 전체행 | 현재값. 시점별 변화는 active_meta_file(metric_code='record_count')

    column_count    INTEGER,
    -- 컬럼 수

    column_names    JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 컬럼명 목록 | JOINABLE / SCHEMA_SIMILAR 판정의 1차 필터

    column_profile  JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 항목별 기술통계량
    -- 컬럼별 타입·결측률·범위(수치형)·카디널리티와 상위값(범주형)
    -- [협력기관] KOSIS는 분류별 값·항목별 단위가 들어간다

    -- ── 수록 기간 ─────────────────────────────────────────────
    coverage_start  DATE,
    -- 수록기간 시작 | TIMESERIES_SUCCESSOR 판정 근거

    coverage_end    DATE,
    -- 수록기간 종료 | [협력기관] 공공데이터는 파일명 날짜 접미가 이 값이다

    -- ── 분류·요약 ─────────────────────────────────────────────
    domain          TEXT,
    -- 도메인 | [협력기관] 대표 대분류 — dcat_dataset.category 첫 번째 값의 대분류
    -- 예) category=["의료 > 질병관리", ...] → domain='의료'
    -- 공통 분류표는 database/category_taxonomy.md 참조

    table_summary   TEXT,
    -- 상세 요약 | 임베딩 소스 텍스트 (meta_datagokr_file_vec.summary_embedding)

    -- ── 관리 ──────────────────────────────────────────────────
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_meta_datagokr_file_name ON meta_datagokr_file (file_name);
CREATE INDEX idx_meta_datagokr_file_dataset ON meta_datagokr_file (dataset_id);
CREATE INDEX idx_meta_datagokr_file_domain  ON meta_datagokr_file (domain);
CREATE INDEX idx_meta_datagokr_file_columns ON meta_datagokr_file USING GIN (column_names);
