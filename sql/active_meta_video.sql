-- ═══════════════════════════════════════════════════════════════
-- active_meta_video : YouTube 영상 시계열 통계 스냅샷
-- meta_video.id (= dataset+video 조합) 단위로 추적
-- 같은 video가 여러 dataset에 속하면 각각 독립적인 수집 타임라인 유지
-- 수집 주기마다 INSERT (누적 이력, UPDATE 없음)
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_video;

CREATE TABLE active_meta_video (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    meta_id         BIGINT NOT NULL
                    REFERENCES meta_video(id) ON DELETE CASCADE,
    -- meta_video.id FK (dataset+video 조합을 가리킴)
    -- ON DELETE CASCADE: 영상 메타 삭제 시 통계 이력도 함께 삭제

    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 이 통계를 수집한 시각

    UNIQUE (meta_id, collected_at),
    -- 동일 meta_id를 같은 시각에 중복 수집 방지

    -- ── 통계 스냅샷 ───────────────────────────────────────────
    view_count      BIGINT,
    -- schema:interactionStatistic(WatchAction) | 조회수

    like_count      BIGINT,
    -- schema:interactionStatistic(LikeAction) | 좋아요 수

    comment_count   BIGINT,
    -- schema:commentCount | 댓글 수

    -- ── 전 회차 대비 증감 ─────────────────────────────────────
    -- NULL = 이 meta_id의 첫 번째 수집 (기준값 없음)
    -- 기준: 동일 meta_id의 직전 collected_at 행
    delta_views     BIGINT,
    delta_likes     BIGINT,
    delta_comments  BIGINT
);

-- 조회용 인덱스
CREATE INDEX idx_active_yt_meta       ON active_meta_video(meta_id);
CREATE INDEX idx_active_yt_collected  ON active_meta_video(collected_at DESC);
