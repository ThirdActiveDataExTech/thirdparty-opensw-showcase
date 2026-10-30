-- ═══════════════════════════════════════════════════════════════
-- active_meta_persona_insight : 네이버 쇼핑 인사이트 Persona 일별 지수
-- source_type = 'persona_insight'
--
-- 수집 주기마다 INSERT (누적 이력, UPSERT). 1행 = 카테고리 × 날짜 × 성별 × 연령.
--
-- [API 호출 구조]
--   카테고리 1개당 2회 호출:
--     성별 API (/category/gender) → 날짜별 m/f 원시값
--     연령 API (/category/age)    → 날짜별 10/20/30/40/50/60 원시값
--   두 결과를 cross-product → 12조합(2성별 × 6연령) 행 생성
--
-- [persona_index 계산]
--   persona_index = gender_pv × age_pv
--   단, 성별과 연령이 독립(independence assumption)이라는 가정 하의 추정치.
--   실측 교차분포(joint distribution)가 아님에 유의.
--
-- [scale 계산]
--   gender_scale : 이전 수집의 gender_ratio와 신규의 gender_ratio 비율 중앙값
--                  남성/여성 시리즈를 stacking(2N 포인트)해 노이즈 강건성 확보
--   age_scale    : 6개 연령 시리즈 stacking(6N 포인트)으로 계산
--   → shopping_insight의 단일 scale_factor와 달리 성별/연령 축을 분리해서 보정
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_persona_insight;

CREATE TABLE active_meta_persona_insight (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    meta_id         BIGINT NOT NULL
                    REFERENCES meta_persona_insight(id) ON DELETE CASCADE,

    period          DATE NOT NULL,
    -- 측정 날짜

    gender          TEXT NOT NULL,
    -- 'm' = 남성, 'f' = 여성
    -- shopping_insight와 달리 전체('')값 없음 — 항상 m/f 분리

    age             TEXT NOT NULL,
    -- '10'/'20'/'30'/'40'/'50'/'60' 고정 6개
    -- shopping_insight와 달리 전체('')값 없음 — 항상 연령대 분리

    UNIQUE (meta_id, period, gender, age),

    -- ── API 원시값 ────────────────────────────────────────────
    gender_ratio    REAL,
    -- 성별 API(/category/gender) 반환값
    -- 해당 (gender, period)의 원시 검색량 지수
    -- inter_scale 재계산 시 참조용으로 저장

    age_ratio       REAL,
    -- 연령 API(/category/age) 반환값
    -- 해당 (age, period)의 원시 검색량 지수
    -- inter_scale 재계산 시 참조용으로 저장

    -- ── 수집 간 보정 스케일 ───────────────────────────────────
    gender_scale    REAL NOT NULL DEFAULT 1.0,
    -- 이전 수집 대비 성별 API M 차이 보정 계수
    -- 남성+여성 시리즈 stacking → 2N 포인트 중앙값
    -- 첫 수집 = 1.0

    age_scale       REAL NOT NULL DEFAULT 1.0,
    -- 이전 수집 대비 연령 API M 차이 보정 계수
    -- 10/20/30/40/50/60 시리즈 stacking → 6N 포인트 중앙값
    -- 첫 수집 = 1.0

    -- ── 보정 적용값 ───────────────────────────────────────────
    gender_pv       REAL,
    -- gender_ratio × gender_scale
    -- 수집 구간 간 비교 가능한 성별 검색량 지수

    age_pv          REAL,
    -- age_ratio × age_scale
    -- 수집 구간 간 비교 가능한 연령 검색량 지수

    persona_index   REAL,
    -- gender_pv × age_pv
    -- 독립 가정 기반 (gender, age) 조합 추정 수요 지수
    -- gender_pv 또는 age_pv 가 NULL이면 NULL

    -- ── 수집 메타 ─────────────────────────────────────────────
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_active_persona_meta      ON active_meta_persona_insight(meta_id);
CREATE INDEX idx_active_persona_period    ON active_meta_persona_insight(period DESC);
CREATE INDEX idx_active_persona_gender    ON active_meta_persona_insight(gender);
CREATE INDEX idx_active_persona_age       ON active_meta_persona_insight(age);
CREATE INDEX idx_active_persona_collected ON active_meta_persona_insight(collected_at DESC);
