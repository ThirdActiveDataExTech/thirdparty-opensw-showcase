-- ═══════════════════════════════════════════════════════════════
-- metadata_entry : 미분류 항목
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [기존 테이블 유지]
-- 카탈로그·현황·파일 세 갈래로 분류되지 않는 원본 속성의 이름/값을 수용한다.
--
-- 주의: datagokr DB에 원래 있던 테이블로, metadata-ingestion이 만든 것이 아니다.
--       별첨에서 재사용 대상으로 지정되어 이 저장소에도 정의를 기록해 둔다.
--       FK가 없으므로 metadata_id는 참조 무결성이 보장되지 않는다.
--
-- 모비젠 의견(NEXT_STEPS.md §7.5): 재사용 재검토 요청 — 원본은 이미 SeaweedFS raw +
--   JSON-LD + dcat_dataset_draft.raw_storage_key에 있다. 별도 EAV 재적재의 실익을
--   다시 보고, 필요하면 raw_metadata jsonb로 갈음하는 쪽을 제안했다.
-- ═══════════════════════════════════════════════════════════════
-- 운영 중 데이터(2026-10-27 기준 316행)가 있으므로 DROP하지 않는다.
-- 신규 환경 구축 시에만 아래 CREATE를 사용한다.

CREATE TABLE IF NOT EXISTS metadata_entry (

    id              SERIAL PRIMARY KEY,
    -- 엔트리 ID

    metadata_id     TEXT NOT NULL,
    -- 메타데이터 ID | 원본 메타데이터 묶음 식별자

    metadata_schema TEXT NOT NULL,
    -- 속성명 | 원본 속성 경로/이름 (예: listTitleNm)

    value           TEXT,
    -- 값

    ingested_at     TIMESTAMPTZ DEFAULT now()
    -- 수집 시각
);
