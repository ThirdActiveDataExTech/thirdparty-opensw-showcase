-- ═══════════════════════════════════════════════════════════════
-- active_meta_news : Naver 뉴스 기사 시계열 통계 스냅샷
-- is_naver_hosted=TRUE 인 기사만 수집 가능
-- 외부 기사(is_naver_hosted=FALSE)는 row 없음
-- 수집 주기마다 INSERT (누적 이력, UPDATE 없음)
--
-- [수집 가능 지표 결정 배경]
-- 조회수  : 네이버가 2020년 이후 완전 폐지, 수집 불가
-- 추천 반응(쏠쏠정보·공감백배 등): HTML에 존재하나 JS 실행 후 로드되는
--           구조로 서버사이드 스크래핑/API 직접 호출로는 항상 0 반환.
--           Selenium/Playwright 같은 브라우저 자동화 없이는 수집 불가
-- 댓글 수 : 비공식 API(apis.naver.com/commentBox/cbox5) 로 수집 가능
--           → 댓글 수(comment_count)·노출 댓글 수(expose_count)·답글 수(reply_count) 만 수집
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_news;

CREATE TABLE active_meta_news (

    -- ── 식별 ──────────────────────────────────────────────────
    id              BIGSERIAL PRIMARY KEY,

    meta_id         BIGINT NOT NULL
                    REFERENCES meta_news(id) ON DELETE CASCADE,
    -- meta_news.id FK (dataset+기사 조합)
    -- is_naver_hosted=TRUE 인 기사만 행 존재

    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (meta_id, collected_at),

    -- ── 댓글 통계 스냅샷 ──────────────────────────────────────
    comment_count   INTEGER,
    -- 전체 댓글 수 (삭제 포함)
    -- 비공식 API: result.count.comment

    expose_count    INTEGER,
    -- 실제 노출 중인 댓글 수 (삭제·숨김 제외)
    -- 비공식 API: result.count.exposeCount

    reply_count     INTEGER,
    -- 답글 수
    -- 비공식 API: result.count.reply

    -- ── 전 회차 대비 증감 ─────────────────────────────────────
    -- NULL = 이 meta_id의 첫 번째 수집 (기준값 없음)
    delta_comments  INTEGER
);

-- 조회용 인덱스
CREATE INDEX idx_active_news_meta      ON active_meta_news(meta_id);
CREATE INDEX idx_active_news_collected ON active_meta_news(collected_at DESC);
