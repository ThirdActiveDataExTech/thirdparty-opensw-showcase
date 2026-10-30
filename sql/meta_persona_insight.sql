-- ═══════════════════════════════════════════════════════════════
-- meta_persona_insight : 네이버 쇼핑 인사이트 Persona 카테고리 정적 정보
-- source_type = 'persona_insight'
--
-- 수집 대상 카테고리 목록을 저장하는 메타 테이블.
-- 실제 측정값(날짜 × 성별 × 연령별 persona_index)은 active_meta_persona_insight에 적재.
--
-- [shopping_insight와의 차이]
-- shopping_insight : anchor 개념 있음, 배치 호출, 1 API
-- persona_insight  : anchor 없음, 카테고리별 독립 호출, 2 API(gender + age)
--                    → is_anchor 컬럼 없음
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_persona_insight CASCADE;

CREATE TABLE meta_persona_insight (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    dataset_id      TEXT NOT NULL
                    REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,

    category_id     TEXT NOT NULL,
    -- 네이버 쇼핑 카테고리 코드 (예: '50000148')

    UNIQUE (dataset_id, category_id),

    -- ── 카테고리 정보 ─────────────────────────────────────────
    category_name   TEXT NOT NULL,
    -- 전체 경로명 (예: '패션의류>남성의류>정장')

    cat_level1      TEXT,
    -- 1차 분류 (예: '패션의류')
    cat_level2      TEXT,
    -- 2차 분류 (예: '남성의류')
    cat_level3      TEXT,
    -- 3차 분류 (예: '정장')
    cat_level4      TEXT,
    -- 4차 분류 (대부분 NULL)

    -- ── 관리 ──────────────────────────────────────────────────
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 이 카테고리가 수집 대상으로 등록된 시각

    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    -- category_name/cat_level* 갱신 시각 (네이버 카테고리 개편 시 대비)
);

CREATE INDEX idx_persona_dataset ON meta_persona_insight(dataset_id);
CREATE INDEX idx_persona_cat_id  ON meta_persona_insight(category_id);
CREATE INDEX idx_persona_level1  ON meta_persona_insight(cat_level1);
