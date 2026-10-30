-- ═══════════════════════════════════════════════════════════════
-- active_meta_shopping_insight : 네이버 쇼핑 인사이트 일별 검색량 지수
-- source_type = 'shopping_insight'
--
-- 수집 주기마다 INSERT (누적 이력, UPSERT). 1행 = 카테고리 × 날짜 × 성별 × 연령.
--
-- [저장값 3종]
--   raw_ratio        : API 원시값. 같은 호출 내 최댓값=100 기준 상대값.
--                      배치가 달라지면 M(최댓값)이 바뀌므로 배치/구간 간 비교 불가.
--   normalized_ratio : raw_ratio / anchor_raw_ratio × 100.
--                      배치 간 비교 가능. anchor 카테고리 자신은 항상 100.0.
--   pseudo_volume    : raw_ratio × scale_factor.
--                      배치 간·수집 구간 간 모두 비교 가능한 연속 시계열.
--                      실제 검색량에 비례 (비례 상수는 알 수 없음).
--
-- [scale_factor 계산 원리]
--   scale_factor = intra_scale × inter_scale
--   ┌ intra_scale : 동일 수집 내 배치 간 M 차이 보정
--   │   = median(ref_anchor_raw[t] / batch_anchor_raw[t])  (기준=첫 번째 유효 배치)
--   └ inter_scale : 수집 구간 간 M 차이 보정
--       = median(db_anchor_raw[t] / new_anchor_raw[t])  (겹치는 기간 이용)
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_shopping_insight;

CREATE TABLE active_meta_shopping_insight (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    meta_id         BIGINT NOT NULL
                    REFERENCES meta_shopping_insight(id) ON DELETE CASCADE,
    -- meta_shopping_insight.id FK (dataset+카테고리 조합)

    period          DATE NOT NULL,
    -- 측정 날짜 (API timeUnit=date 기준)
    -- SQLite 원본의 period TEXT('2025-06-17') → DATE 변환

    gender          TEXT NOT NULL,
    -- 성별 필터 값
    -- 'm' = 남성, 'f' = 여성, '' = 전체(필터 없음)

    age             TEXT NOT NULL,
    -- 연령 필터 값
    -- '10'/'20'/'30'/'40'/'50'/'60' = 해당 연령대, '' = 전체(필터 없음)
    -- (config.yaml 기준 6개 연령대 — 성별 2 × 연령 6 = 12조합/카테고리)

    UNIQUE (meta_id, period, gender, age),
    -- 같은 카테고리+날짜+성별+연령 조합은 최신 수집값으로 UPSERT

    -- ── API 원시값 ────────────────────────────────────────────
    raw_ratio       REAL NOT NULL,
    -- API 반환 원시 ratio (호출 내 최대값=100 기준)
    -- 배치·수집 구간이 달라지면 비교 불가

    anchor_raw_ratio REAL,
    -- 같은 (gender, age, period)에서 anchor 카테고리의 raw_ratio
    -- anchor 카테고리 자신의 행에서는 raw_ratio와 동일
    -- 정규화 및 scale 재계산 시 참조용

    -- ── 보정값 ───────────────────────────────────────────────
    normalized_ratio REAL,
    -- raw_ratio / anchor_raw_ratio × 100
    -- anchor 카테고리 자신은 100.0 고정
    -- anchor_raw_ratio 가 NULL이면 NULL

    scale_factor    REAL,
    -- intra_scale × inter_scale (첫 수집=1.0)
    -- NULL: scale 계산 전 수집분 (구버전 호환)

    pseudo_volume   REAL,
    -- raw_ratio × scale_factor
    -- 장기 연속 시계열 비교용. scale_factor가 NULL이면 NULL

    -- ── 수집 메타 ─────────────────────────────────────────────
    batch_index     INTEGER,
    -- 동일 수집 내 배치 번호 (0-based)
    -- API가 최대 3카테고리/호출이므로 카테고리가 많을수록 배치 수 증가
    -- 디버깅·intra_scale 추적용

    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    -- 수집 스크립트 실행 시각 (ISO8601)
);

CREATE INDEX idx_active_shopping_meta      ON active_meta_shopping_insight(meta_id);
CREATE INDEX idx_active_shopping_period    ON active_meta_shopping_insight(period DESC);
CREATE INDEX idx_active_shopping_gender    ON active_meta_shopping_insight(gender);
CREATE INDEX idx_active_shopping_age       ON active_meta_shopping_insight(age);
CREATE INDEX idx_active_shopping_collected ON active_meta_shopping_insight(collected_at DESC);
