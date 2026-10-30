-- ═══════════════════════════════════════════════════════════════
-- active_meta_blog : Naver 블로그 게시물 시계열 통계 스냅샷
-- ADR-006(Naver 블로그 수집 가능 지표 결정)으로 확정 — 반응(공감 등) 수만 수집.
-- 댓글 수·조회수는 실제 API 검증 결과 수집 불가/보류로 결론 (ADR-006 참조).
--
-- 반응 수 API: blog.like.naver.com/v1/search/contents?q=BLOG[{blogId}_{logNo}]
-- (Referer 헤더만 있으면 세션/쿠키 없이 수집 가능 — 뉴스의 "추천 반응"과 달리
--  브라우저 자동화 불필요)
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_blog;

CREATE TABLE active_meta_blog (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    meta_id         BIGINT NOT NULL
                    REFERENCES meta_blog(id) ON DELETE CASCADE,
    -- meta_blog.id FK (dataset+게시물 조합)
    -- meta_blog.platform='naver'인 게시물만 행 존재 (news의 is_naver_hosted와 유사한 제약)

    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (meta_id, collected_at),

    -- ── 반응 수 (ADR-006으로 수집 확정) ───────────────────────
    reaction_count      INTEGER NOT NULL DEFAULT 0,
    -- 전체 반응 수 합계 (공감/칭찬해요/웃김/슬픔/놀람/감사 6종 합)

    reaction_breakdown  JSONB,
    -- 반응 타입별 세부 카운트. 예: {"like": 32, "impressive": 1}
    -- 키는 API 응답의 reactionType 값 그대로 (like/impressive/thanks/haha/sad/wow)

    -- ── 전 회차 대비 증감 ─────────────────────────────────────
    -- NULL = 이 meta_id의 첫 번째 수집 (기준값 없음)
    delta_reactions     INTEGER
);

-- 조회용 인덱스
CREATE INDEX idx_active_blog_meta      ON active_meta_blog(meta_id);
CREATE INDEX idx_active_blog_collected ON active_meta_blog(collected_at DESC);
