-- ═══════════════════════════════════════════════════════════════
-- meta_file_relation : 데이터파일·컬럼 간 관계
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 컬럼명이 NULL이면 파일 간 관계, 값이 있으면 컬럼 간 관계로 해석한다.
--
-- 산출 주체: 컬럼 관계 산출은 협력기관 알고리즘이 담당한다 (NEXT_STEPS.md §7.4).
--   데이터셋 관계(dcat_dataset_relation)로 후보 쌍을 좁힌 뒤 종속 산출한다.
--   조합 폭발과 도메인 교차 오탐을 막기 위한 설계이며 우리 스키마 조치는 없다.
-- 출처 통합: 협력기관 DDL과 통합한 정본. 원본은 협력기관 수신본  참조.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_file_relation CASCADE;

CREATE TABLE meta_file_relation (

    id              BIGSERIAL PRIMARY KEY,
    -- 관계 ID

    source_file_id  TEXT NOT NULL
                    REFERENCES meta_datagokr_file(file_id) ON DELETE CASCADE,
    -- 출발 파일

    source_column   TEXT,
    -- 출발 컬럼명 | NULL이면 파일 단위 관계

    target_file_id  TEXT NOT NULL
                    REFERENCES meta_datagokr_file(file_id) ON DELETE CASCADE,
    -- 도착 파일

    target_column   TEXT,
    -- 도착 컬럼명 | NULL이면 파일 단위 관계

    relation_type   TEXT NOT NULL
                    REFERENCES relation_type_registry(relation_type) ON UPDATE CASCADE,
    -- 관계 유형 | relation_type_registry 참조
    -- 파일 계층 유형: TIMESERIES_SUCCESSOR(시계열 연속), COLUMN_NAME_SIMILAR(컬럼명 유사)

    score           REAL NOT NULL,
    -- 관계 점수 | 0~1

    evidence        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 판정 근거 | [협력기관] 값 중첩률, 타입 일치, 명칭 유사도

    status          TEXT NOT NULL,
    -- 검토 상태 | PENDING / APPROVED / REJECTED

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE NULLS NOT DISTINCT
        (source_file_id, source_column, target_file_id, target_column, relation_type)
    -- NULLS NOT DISTINCT: 컬럼명이 NULL(파일 단위)인 조합도 중복으로 판정한다
    -- (PostgreSQL 15+ 문법)
);

CREATE INDEX idx_meta_file_relation_type   ON meta_file_relation (relation_type);
CREATE INDEX idx_meta_file_relation_target ON meta_file_relation (target_file_id);
