-- ═══════════════════════════════════════════════════════════════
-- meta_shopping_insight : 네이버 쇼핑 인사이트 카테고리 정적 정보
-- source_type = 'shopping_insight'
--
-- 수집 대상 카테고리 목록을 저장하는 메타 테이블.
-- 실제 측정값(날짜 × 성별 × 연령별 검색량 지수)은 active_meta_shopping_insight에 적재.
--
-- [anchor 개념]
-- 네이버 쇼핑인사이트 API는 한 번에 최대 3개 카테고리를 비교하며,
-- 그 중 가장 높은 값이 100이 되도록 정규화(M 기준)된 상대값을 반환한다.
-- 배치마다 M이 달라지므로 배치 간 비교를 위해 anchor(기준 카테고리) 1개를
-- 모든 배치에 포함시킨다. is_anchor=TRUE 인 카테고리가 기준점이다.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_shopping_insight CASCADE;

CREATE TABLE meta_shopping_insight (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    dataset_id      TEXT NOT NULL
                    REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,

    category_id     TEXT NOT NULL,
    -- 네이버 쇼핑 카테고리 코드 (예: '50000148')
    -- API 파라미터의 param 값과 동일

    UNIQUE (dataset_id, category_id),

    -- ── 카테고리 정보 ─────────────────────────────────────────
    category_name   TEXT NOT NULL,
    -- 전체 경로명 (예: '패션의류>남성의류>정장')
    -- API 파라미터의 name 값과 동일, 구분자 '>'

    cat_level1      TEXT,
    -- 1차 분류 (예: '패션의류')
    cat_level2      TEXT,
    -- 2차 분류 (예: '남성의류')
    cat_level3      TEXT,
    -- 3차 분류 (예: '정장')
    cat_level4      TEXT,
    -- 4차 분류 (대부분 NULL)

    -- ── anchor 여부 ───────────────────────────────────────────
    is_anchor       BOOLEAN NOT NULL DEFAULT FALSE,
    -- TRUE: 이 카테고리가 배치 간 정규화 기준(anchor)
    -- 데이터셋당 정확히 1개의 카테고리만 TRUE (아래 partial unique index로 "최대 1개"는
    -- DB가 보장하고, "최소 1개"는 수집 코드가 anchor_category 설정을 항상 포함시켜 보장한다)
    -- config.yaml anchor_category 설정값과 대응

    -- ── 관리 ──────────────────────────────────────────────────
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 이 카테고리가 수집 대상으로 등록된 시각

    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    -- category_name/cat_level* 갱신 시각 (네이버 카테고리 개편 시 대비)
);

CREATE INDEX idx_shopping_dataset  ON meta_shopping_insight(dataset_id);
CREATE INDEX idx_shopping_cat_id   ON meta_shopping_insight(category_id);
CREATE INDEX idx_shopping_anchor   ON meta_shopping_insight(is_anchor);
CREATE INDEX idx_shopping_level1   ON meta_shopping_insight(cat_level1);

-- 데이터셋당 anchor 카테고리는 최대 1개만 허용 (partial unique index)
CREATE UNIQUE INDEX idx_shopping_one_anchor
    ON meta_shopping_insight(dataset_id)
    WHERE is_anchor = TRUE;
