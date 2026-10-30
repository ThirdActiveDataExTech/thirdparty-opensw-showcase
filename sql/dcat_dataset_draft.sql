-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset_draft : 표준 매핑 초안 (재수집 1회당 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 자동 확정 기준에 미달한 매핑의 검토 대기 큐 + 매핑 증거.
-- 원본 스냅샷 참조를 겸한다(원본 실체는 SeaweedFS raw에 있고 여기엔 키만 둔다).
--
-- 모비젠 의견(NEXT_STEPS.md §7.5): metadata_entry(미분류 EAV) 재사용은 재검토 요청.
--   원본은 이미 SeaweedFS raw + JSON-LD + 이 테이블의 raw_storage_key에 있으므로
--   별도 EAV 재적재의 실익을 다시 보자는 취지. 필요 시 raw_metadata jsonb로 갈음.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS dcat_dataset_draft CASCADE;

CREATE TABLE dcat_dataset_draft (

    id                BIGSERIAL PRIMARY KEY,
    -- 초안 ID

    source            TEXT NOT NULL,
    -- 출처 | 원천 포털 코드 (DATA_GO_KR / KOSIS / FIRST_PARTY)

    payload_sha256    TEXT NOT NULL UNIQUE,
    -- 원본 해시 | 중복·변경 감지

    raw_storage_key   TEXT NOT NULL,
    -- 원본 보관 경로 | SeaweedFS S3 키 · 재처리 원본

    mapping_version   TEXT NOT NULL,
    -- 매핑 버전 | 매핑 규칙 버전

    status            TEXT NOT NULL DEFAULT 'PENDING',
    -- 상태 | PENDING / PUBLISHED / DISCARDED

    content           JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- DCAT 콘텐츠 필드 | title · description · publisher 등 dcat_dataset과 동일 구성
    -- 확정 전이라 개별 컬럼으로 펼치지 않고 jsonb로 보관한다

    mapping_evidence  JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 매핑 증거 | 속성별 top-k 후보와 점수 · 등재 검토 화면의 원본

    auto_threshold    REAL,
    -- 자동 확정 기준값 | 적용 기준선 · 초기값 0.90

    reviewed_by       TEXT,
    -- 판정자

    reviewed_at       TIMESTAMPTZ,
    -- 판정 시각

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dcat_dataset_draft_source          ON dcat_dataset_draft (source);
CREATE INDEX idx_dcat_dataset_draft_status          ON dcat_dataset_draft (status);
CREATE INDEX idx_dcat_dataset_draft_mapping_version ON dcat_dataset_draft (mapping_version);
