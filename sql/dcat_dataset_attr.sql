-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset_attr : 데이터셋 현황 메타데이터 (데이터셋 1건 = 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- DCAT에 대응 용어가 없는 정형 고유 항목 17종을 분리 보관한다. 검색 필터의 원본.
-- 공공데이터포털 '목록개방현황' 항목 중 카탈로그(dcat_dataset)에 들어가지 않는 것들.
--
-- 비정형(video/news/blog/shopping/persona)은 이 테이블을 사용하지 않는다.
-- 출처 통합: 협력기관 DDL과 통합한 정본. 원본은 협력기관 수신본  참조.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS dcat_dataset_attr CASCADE;

CREATE TABLE dcat_dataset_attr (

    dataset_id              TEXT PRIMARY KEY
                            REFERENCES dcat_dataset(dataset_id)
                            ON UPDATE CASCADE ON DELETE CASCADE,
    -- 데이터셋 식별자 | dcat_dataset 참조 (1:1)
    -- ON UPDATE CASCADE: dataset_id URN 전환 시 자동 전파된다

    -- ── 목록 구분 ─────────────────────────────────────────────
    list_type               TEXT,
    -- 목록유형 | [협력기관] FILE / API / STD / STAT(KOSIS 통계표)
    -- ※ 별첨 v2는 FILE/API/LINK였으나 KOSIS 합류로 개정됐다. 협력기관 DDL 기준을 따른다.

    stat_name               TEXT,
    -- 통계명 | KOSIS 통계명. 같은 통계에 속한 통계표를 묶는 데 쓴다
    -- (별첨 v2 정의서에 없던 컬럼 — 협력기관 메모로 용도 확인, 2026-10-27)

    spatial_unit            TEXT,
    -- 집계 단위 | 데이터의 공간 집계 단위
    -- 값) NATION(전국) / SIDO(시도) / SIGUNGU(시군구) / EMD(읍면동)
    -- (별첨 v2 정의서에 없던 컬럼 — 협력기관 메모로 용도 확인, 2026-10-27)

    -- ── 갱신 ──────────────────────────────────────────────────
    next_registration_date  DATE,
    -- 차기 등록 예정일 | 원천이 공시하는 값
    -- 주의: 스케줄러 실행 시각(data_registry.next_collect_at)과 구분해 보관한다
    --       next_collect_at 산정 시 "예정일 우선 → accrual_periodicity → 주간" 순으로 참고

    -- ── 제공 형태 ─────────────────────────────────────────────
    media_type              TEXT,
    -- 매체유형

    provision_form          TEXT,
    -- 제공형태 | 포털 다운로드 / 기관 URL 등

    api_type                TEXT,
    -- API 유형

    allowed_traffic         TEXT,
    -- 신청가능 트래픽 | [협력기관] 원문이 문장이라 text
    -- (별첨은 integer로 기술하나 원천 값에 단위 문자열이 섞여 들어와 TEXT로 생성됨)

    review_type             TEXT,
    -- 심의 유형

    -- ── 분류 플래그 ───────────────────────────────────────────
    national_core_yn        BOOLEAN,
    -- 국가중점여부 | 원본 Y/N을 boolean으로 변환

    standard_data_yn        BOOLEAN,
    -- 표준데이터여부 | 표준데이터셋 식별

    -- ── 비용 ──────────────────────────────────────────────────
    cost_charged            TEXT,
    -- 비용부과유무 | 무료 / 유료

    cost_basis              TEXT,
    -- 비용부과기준 및 단위

    -- ── 담당 부서 ─────────────────────────────────────────────
    dept_name               TEXT,
    -- 관리 부서명

    dept_phone              TEXT,
    -- 관리부서 전화번호

    -- ── 결측이 잦은 항목 (필수로 두지 않는다) ─────────────────
    retention_basis         TEXT,
    -- 보유근거 | [협력기관] 법적 근거

    collection_method       TEXT,
    -- 수집방법 | [협력기관] 작성방법

    data_limitation         TEXT,
    -- 데이터 한계

    other_notes             TEXT,
    -- 기타 유의사항 | [협력기관] 통계표 주석

    -- ── 관리 ──────────────────────────────────────────────────
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    -- 갱신 시각
);

-- 검색 필터용
CREATE INDEX idx_dcat_dataset_attr_list_type ON dcat_dataset_attr (list_type);
CREATE INDEX idx_dcat_dataset_attr_stat_name ON dcat_dataset_attr (stat_name);
