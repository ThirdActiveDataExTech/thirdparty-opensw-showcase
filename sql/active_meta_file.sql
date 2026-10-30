-- ═══════════════════════════════════════════════════════════════
-- active_meta_file : 데이터파일 이력 메타데이터 (관측 1건 = 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 구조는 active_meta_dataset과 동일하고 참조 대상만 다르다.
-- 포털 다운로드 수 환류 대상.
--
-- 적용 범위: 정형 전용이다. meta_datagokr_file을 참조하므로 비정형 아이템
-- 출처 통합: 협력기관 DDL 4(지표 표준값)와 통합한 정본.
--   원본: 협력기관 수신본 4_지표_표준값.sql
--
-- (영상·기사·게시물)은 적재할 수 없으며, 비정형은 기존 active_meta_video /
-- active_meta_news / active_meta_blog 등을 그대로 사용한다.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_file CASCADE;

CREATE TABLE active_meta_file (

    id              BIGSERIAL PRIMARY KEY,
    -- 관측 ID

    file_id         TEXT NOT NULL
                    REFERENCES meta_datagokr_file(file_id) ON DELETE CASCADE,
    -- 데이터파일 식별자 | meta_datagokr_file 참조

    metric_code     TEXT NOT NULL
                    REFERENCES metric_registry(metric_code) ON UPDATE CASCADE,
    -- 지표 코드 | metric_registry 참조 (layer='file'인 코드만 적재)

    metric_value    NUMERIC(20,4) NOT NULL,
    -- 관측값 | 그 시점의 값

    observed_at     TIMESTAMPTZ NOT NULL,
    -- 관측 시각

    source          TEXT NOT NULL,
    -- 수집 출처 | PORTAL_LOG / CRAWLER

    UNIQUE (file_id, metric_code, observed_at)
);
