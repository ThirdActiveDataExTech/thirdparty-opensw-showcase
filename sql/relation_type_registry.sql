-- ═══════════════════════════════════════════════════════════════
-- relation_type_registry : 관계 유형 표준값 (관계 유형 1개 = 1행)
--
-- 출처 통합: 모비젠 제안 → 협력기관 반영. 협력기관 DDL 3(관계 유형 표준값)과 통합한 정본.
--   원본: 협력기관 수신본 3_관계유형_표준값.sql
--
-- [협력기관] dcat_dataset_relation / meta_file_relation 이 참조한다.
--
-- 주의: FK로 묶여 있어 여기에 등록되지 않은 관계 유형은 INSERT 자체가 불가하다.
--       협력기관 회신(2026-10-27): "새 코드는 같은 테이블에 추가한 뒤 사용할 수 있습니다."
--       DDL 주석에도 "비정형 전용 코드는 모비젠이 추가한다"로 명시되어 있다.
--
-- 표준값 개정 경위 (협력기관 메모, 2026-10-27)
--   별첨 [5. 관계 유형 표준값] 시트의 11종을 8종으로 정리했다.
--   - SEMANTICALLY_RELATED / KEYWORD_OVERLAP: 그대로 유지 (비정형 공용)
--   - 정형 데이터셋 간 관계는 '함께 쓰면 무엇을 할 수 있는가' 기준으로 4종 재정리
--   - 파일 간 2종: TIMESERIES_SUCCESSOR, COLUMN_NAME_SIMILAR
--   삭제: SAME_PUBLISHER, JOINABLE, TEMPORAL_OVERLAP, SCHEMA_SIMILAR,
--         COMPLEMENTARY, SPATIAL_OVERLAP, LINEAGE
--
-- 모비젠 운용 방침: 비정형은 우선 SEMANTICALLY_RELATED, KEYWORD_OVERLAP 2종만 활용한다.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS relation_type_registry CASCADE;

CREATE TABLE relation_type_registry (

    relation_type   TEXT PRIMARY KEY,
    -- 관계 유형 코드 | 전역 유일
    -- [협력기관] dcat_dataset_relation.relation_type에는 이 코드만 넣고,
    --            판정 과정에서 나온 구체적 설명은 relation_label에 넣는다

    label           TEXT NOT NULL,
    -- 한글명 | [협력기관] 화면 표기명

    scope           TEXT NOT NULL,
    -- 적용 레이어 | [협력기관] dataset / file / both (저장 테이블 구분)

    applies_to      JSONB NOT NULL,
    -- 적용 소스 유형 | 적용 가능한 source_type 배열. ["*"] = 전체 공통
    -- 2026-10-28 현재 비정형에 적용 가능한 유형은 ["*"]인 2종뿐
    -- (SEMANTICALLY_RELATED, KEYWORD_OVERLAP) — 나머지는 ["structured_file"]

    required_fields JSONB NOT NULL,
    -- 판정 근거 필드 | [협력기관] 판정에 쓰는 항목
    -- 이 필드가 비어 있는 데이터셋은 해당 관계가 산출되지 않는다
    -- 예) SEMANTICALLY_RELATED는 ["title","description"]이 필요하므로
    --     description이 부실하면 관계 자체가 나오지 않는다

    description     TEXT
    -- 설명 | [협력기관] 판정 근거 · 방향
);

CREATE INDEX idx_relation_type_registry_scope   ON relation_type_registry (scope);
CREATE INDEX idx_relation_type_registry_applies ON relation_type_registry USING GIN (applies_to);


-- ── 표준값 시드 (협력기관) ────────────────────────────────────
-- [협력기관] 관계 유형 4종(DETAIL_FOR·STATISTIC_FOR·ADJACENT_TO·SAME_KIND)
--            + 비정형 공용 2종 + 파일 단위 2종. 비정형 전용 코드는 모비젠이 추가한다.
INSERT INTO relation_type_registry (relation_type, label, scope, applies_to, required_fields, description)
VALUES ('DETAIL_FOR', '속성 보완', 'both', '["structured_file"]', '["column_names", "column_profile"]',
        '동일 대상의 추가 속성. 공통 식별 컬럼으로 결합하며 결합 컬럼은 meta_file_relation 에 기록. source = 속성을 주는 쪽, target = 기준'),
       ('STATISTIC_FOR', '집계 맥락', 'dataset', '["structured_file"]', '["column_names", "column_profile"]',
        '비교 기준이 되는 통계. source = 집계표, target = 기준'),
       ('ADJACENT_TO', '인접 맥락', 'dataset', '["structured_file"]', '["title", "description", "keywords"]',
        '연관 주제의 인접 데이터. 대칭'),
       ('SAME_KIND', '동종 판본', 'dataset', '["structured_file"]', '["column_names"]',
        '같은 표준을 따르거나 컬럼 구성이 같은 타 지역·기관 데이터. 대칭'),
       ('SEMANTICALLY_RELATED', '의미 유사', 'dataset', '["*"]', '["title", "description"]',
        '제목·설명 임베딩(dcat_dataset_vec)의 코사인 유사도'),
       ('KEYWORD_OVERLAP', '키워드 유사', 'dataset', '["*"]', '["keywords"]',
        '키워드 집합의 자카드 계수'),
       ('TIMESERIES_SUCCESSOR', '시계열 연속', 'file', '["structured_file"]', '["coverage_start", "coverage_end"]',
        '같은 데이터셋의 수록기간이 이어지는 파일. 컬럼 없이 파일 간 관계로 기록'),
       ('COLUMN_NAME_SIMILAR', '컬럼명 유사', 'file', '["structured_file"]', '["column_names"]',
        '컬럼 논리·물리명의 문자열·의미 유사도. 데이터셋 관계로 후보 쌍을 좁힌 뒤 산출')
ON CONFLICT (relation_type) DO NOTHING;


-- ── 모비젠 추가 제안 (B2 관계 분석 착수 시 등록) ──────────────
-- 비정형에 적용 가능한 표준 유형이 2종뿐이라 아래 2종을 추가한다.
--
-- ※ 등록 시점: development/04_Implementation_Methods.md §3 B2 착수 시.
--   FK로 묶여 있어 등록 전에는 INSERT 자체가 불가능하다.
--   추가 전 협력기관에 공유만 하면 된다(추가 권한은 DDL 주석으로 명시됨).
--
-- INSERT INTO relation_type_registry
--     (relation_type, label, scope, applies_to, required_fields, description) VALUES
-- ('ENTITY_SHARED', '개체 공유', 'dataset', '["*"]'::jsonb, '["keywords"]'::jsonb,
--  '두 데이터셋이 공유하는 개체(키워드·태그·카테고리명)의 수와 비중으로 판정. '
--  '겹친 개체 목록을 evidence에 남겨 추천 근거로 제시한다'),
-- ('TEMPORAL_COMOVEMENT', '시계열 공변동', 'dataset', '["*"]'::jsonb, '["accrual_periodicity"]'::jsonb,
--  '두 데이터셋의 지표 시계열을 일 단위로 리샘플해 1차 차분 후 스피어만 상관으로 판정. '
--  '겹치는 구간 30포인트 이상인 쌍만 산출하고 다중비교 보정(BH FDR)을 적용한다. '
--  '삭제된 TEMPORAL_OVERLAP(기간 중첩)과 달리 "같이 움직이는가"를 본다')
-- ON CONFLICT (relation_type) DO NOTHING;
--
-- 모델 산출 엣지는 유형을 늘리지 않는다 — UNIQUE에 method를 포함하는 방식으로 해결했다
-- (협력기관 수락, 2026-10-28). sql/dcat_dataset_relation.sql 참조.
