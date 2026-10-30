-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset_relation : 데이터셋 간 관계 (쌍+유형+method당 1행)
--
-- 출처 통합: 협력기관 DDL 2(정형 데이터셋) + DDL 5(관계 method 확장)와 통합한 정본.
--   원본: 협력기관 수신본 2_정형_데이터셋.sql, 5_관계_method_확장.sql
--
-- [협력기관] 쌍+유형+method당 1행 · 재생성 시 같은 method 행만 대체 ·
--            정본은 dcat_dataset_relation_canonical 뷰(sql/views.sql)
--
-- 이 테이블이 과제 산출물 "AI 기반 데이터 관계 생성·분석 SW"의 저장 계층이다
-- (development/04_Implementation_Methods.md §3 B2·B3·B4, ADR-012).
--
-- UNIQUE에 method가 들어간 경위 (2026-10-28)
--   원안은 (출발, 도착, 유형) 쌍+유형당 1행이었다. 그 구조에서는 같은 쌍·같은 유형에
--   규칙 산출과 모델 산출을 함께 둘 수 없어, 나중에 적재되는 쪽이 앞의 결과를 덮어쓴다.
--   모비젠이 method를 UNIQUE에 포함하자고 제안했고 협력기관이 수락했다.
--   → 규칙만으로 만든 관계 네트워크와 모델을 포함한 네트워크를 각각 산출해 비교할 수 있다.
--   → 재계산은 method 단위로 한다. 규칙 행만 교체하고 모델 행은 건드리지 않는다.
--
-- 규칙 (별첨 [5. 관계 유형 표준값] 시트 공통 규칙)
--   - 유형 추가: relation_type을 문자열 값으로 저장하므로 유형이 늘어도 스키마를 고치지 않는다.
--     단 relation_type_registry에 FK로 묶여 있어 등록되지 않은 유형은 INSERT 불가
--   - 판정 근거: evidence(jsonb)에 매칭 컬럼·겹친 값 수·유사도·LLM 사유를 남긴다
--   - 확정 상태: status로 자동 확정(APPROVED)과 검토 대기(PENDING)를 구분한다
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS dcat_dataset_relation CASCADE;

CREATE TABLE dcat_dataset_relation (

    id                  BIGSERIAL PRIMARY KEY,
    -- 관계 ID

    source_dataset_id   TEXT NOT NULL
                        REFERENCES dcat_dataset(dataset_id)
                        ON DELETE CASCADE ON UPDATE CASCADE,
    -- 출발 데이터셋
    -- ON UPDATE CASCADE: dataset_id URN 전환이 자동 전파된다

    target_dataset_id   TEXT NOT NULL
                        REFERENCES dcat_dataset(dataset_id)
                        ON DELETE CASCADE ON UPDATE CASCADE,
    -- 도착 데이터셋

    relation_type       TEXT NOT NULL
                        REFERENCES relation_type_registry(relation_type) ON UPDATE CASCADE,
    -- 관계 유형 | 값으로 기록 · relation_type_registry 참조
    -- [협력기관] 관계 유형 정의서 4종(:하위라벨) — 유형 코드만 넣고 설명은 relation_label로
    -- 2026-10-28 기준 비정형에 적용 가능한 유형은 2종
    --   SEMANTICALLY_RELATED (제목·설명 임베딩 코사인 유사도)
    --   KEYWORD_OVERLAP      (키워드 집합 자카드 계수)

    relation_label      TEXT,
    -- 관계 설명 | relation_type에는 표준 코드만, 판정 과정에서 나온 구체적 설명을 여기
    -- [협력기관] '유형:하위라벨' 한 문자열을 유형(표준값 FK) + 하위라벨(개방형)로 나눈 것.
    --            앱은 조회 시 '유형:하위라벨'로 다시 합쳐 다룬다
    -- 예) relation_type='DETAIL_FOR',
    --     relation_label='어린이집-교직원 1:N 참조 (어린이집코드 공통)'
    -- 협력기관 회신: **비정형에서는 비워 두어도 된다**

    score               REAL NOT NULL,
    -- 관계 점수 | 0~1

    method              TEXT NOT NULL,
    -- 생성 방법 | [협력기관] rule / embedding / llm (협력기관) · gnn (모비젠)
    -- UNIQUE에 포함된다 — 같은 쌍·유형에 산출 방법별로 행이 공존한다

    status              TEXT NOT NULL,
    -- 검토 상태 | PENDING / APPROVED / REJECTED

    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 판정 근거 | [협력기관] 매칭 컬럼, 유사도, LLM 사유

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 생성 시각

    CONSTRAINT dcat_dataset_relation_pair_type_method_key
        UNIQUE (source_dataset_id, target_dataset_id, relation_type, method),
    -- 쌍+유형+method당 1행

    CONSTRAINT dcat_dataset_relation_method_check
        CHECK (method IN ('rule', 'embedding', 'llm', 'gnn'))
    -- method 값 통제 — 자유 문자열이면 오타 하나가 중복 행을 만든다
);

CREATE INDEX idx_dcat_dataset_relation_type   ON dcat_dataset_relation (relation_type);
CREATE INDEX idx_dcat_dataset_relation_status ON dcat_dataset_relation (status);
CREATE INDEX idx_dcat_dataset_relation_target ON dcat_dataset_relation (target_dataset_id);

-- 정본 뷰(dcat_dataset_relation_canonical)는 sql/views.sql에 있다.
-- 조회하는 쪽은 이 테이블이 아니라 뷰를 읽는다 — 한 쌍·한 유형에 행이 여러 개이기 때문.
