-- ═══════════════════════════════════════════════════════════════
-- views.sql : 편의 조회용 뷰 모음
-- DDL 적용 이후에 실행
-- ═══════════════════════════════════════════════════════════════

-- ── v_meta_video_latest ─────────────────────────────────────
-- meta_video + active_meta_video 최신 row 결합
-- 영상별 현재 통계(최신 수집값 + 전회차 대비 증감)를 한 번에 조회
CREATE OR REPLACE VIEW v_meta_video_latest AS
SELECT
    m.id,
    m.dataset_id,
    m.video_id,
    m.title,
    m.description,
    m.published_at,
    m.channel_id,
    m.channel_title,
    m.tags,
    m.category_id,
    m.topic_categories,
    m.duration,
    m.duration_seconds,
    m.definition,
    m.default_language,
    m.default_audio_language,
    m.has_caption,
    m.thumbnail_url,
    m.initial_view_count,
    m.initial_like_count,
    m.initial_comment_count,
    m.collected_at,
    a.collected_at  AS latest_collected_at,
    a.view_count    AS latest_view_count,
    a.like_count    AS latest_like_count,
    a.comment_count AS latest_comment_count,
    a.delta_views,
    a.delta_likes,
    a.delta_comments
FROM meta_video m
LEFT JOIN LATERAL (
    SELECT *
    FROM active_meta_video
    WHERE meta_id = m.id
    ORDER BY collected_at DESC
    LIMIT 1
) a ON true;

-- ── v_meta_news_latest ──────────────────────────────────
-- meta_news + active_meta_news 최신 row 결합
-- 기사별 현재 댓글 통계(최신 수집값 + 전회차 대비 증감)를 한 번에 조회
-- is_naver_hosted=FALSE 인 외부 기사는 댓글 컬럼 모두 NULL
CREATE OR REPLACE VIEW v_meta_news_latest AS
SELECT
    m.id,
    m.dataset_id,
    m.article_url,
    m.title,
    m.description,
    m.content,
    m.has_content,
    m.publisher,
    m.naver_url,
    m.is_naver_hosted,
    m.naver_oid,
    m.naver_aid,
    m.published_at,
    m.search_keyword,
    m.collected_at,
    a.collected_at   AS latest_collected_at,
    a.comment_count  AS latest_comment_count,
    a.expose_count   AS latest_expose_count,
    a.reply_count    AS latest_reply_count,
    a.delta_comments
FROM meta_news m
LEFT JOIN LATERAL (
    SELECT *
    FROM active_meta_news
    WHERE meta_id = m.id
    ORDER BY collected_at DESC
    LIMIT 1
) a ON true;

-- ── v_meta_blog_latest ──────────────────────────────────
-- meta_blog + active_meta_blog 최신 row 결합
-- 게시물별 현재 반응(공감 등) 통계(최신 수집값 + 전회차 대비 증감)를 한 번에 조회
-- platform!='naver' 게시물은 반응 수집 대상이 아니라 active 행이 없어 반응 컬럼 NULL (ADR-006)
CREATE OR REPLACE VIEW v_meta_blog_latest AS
SELECT
    m.id,
    m.dataset_id,
    m.post_url,
    m.title,
    m.description,
    m.content,
    m.has_content,
    m.blogger_name,
    m.blogger_link,
    m.platform,
    m.blog_id,
    m.log_no,
    m.published_at,
    m.search_keyword,
    m.collected_at,
    a.collected_at       AS latest_collected_at,
    a.reaction_count     AS latest_reaction_count,
    a.reaction_breakdown AS latest_reaction_breakdown,
    a.delta_reactions
FROM meta_blog m
LEFT JOIN LATERAL (
    SELECT *
    FROM active_meta_blog
    WHERE meta_id = m.id
    ORDER BY collected_at DESC
    LIMIT 1
) a ON true;

-- ── v_meta_shopping_insight_latest ──────────────────────────────
-- meta_shopping_insight + active_meta_shopping_insight "최신 날짜 스냅샷"
-- 카테고리별 max(period)의 12조합(성별 m/f × 연령 10~60)만 반환 (long 형태).
-- youtube/news/blog 뷰의 "아이템당 최신 1행"과 달리, 여기선 카테고리당 12행이다
-- (active가 카테고리×날짜×성별×연령 다차원 시계열이라 "최신 1행"이 성립 안 함).
-- 전체('') 집계 행은 의도적으로 제외 — 필요해지면 이 뷰의 IN 필터만 바꾸면 됨(원본 데이터엔 그대로 있음).
CREATE OR REPLACE VIEW v_meta_shopping_insight_latest AS
SELECT
    m.id,
    m.dataset_id,
    m.category_id,
    m.category_name,
    m.is_anchor,
    a.period,
    a.gender,
    a.age,
    a.pseudo_volume,
    a.normalized_ratio
FROM meta_shopping_insight m
LEFT JOIN LATERAL (
    SELECT s.period, s.gender, s.age, s.pseudo_volume, s.normalized_ratio
    FROM active_meta_shopping_insight s
    WHERE s.meta_id = m.id
      AND s.gender IN ('m','f') AND s.age IN ('10','20','30','40','50','60')
      AND s.period = (
          SELECT max(s2.period) FROM active_meta_shopping_insight s2
          WHERE s2.meta_id = m.id AND s2.gender IN ('m','f')
            AND s2.age IN ('10','20','30','40','50','60')
      )
) a ON true;

-- ── v_meta_persona_insight_latest ───────────────────────────────
-- meta_persona_insight + active_meta_persona_insight "최신 날짜 스냅샷"
-- 카테고리별 max(period)의 12조합(성별 m/f × 연령 10~60) persona_index (long 형태).
-- Persona는 성별×연령이 핵심 지표(persona_index = gender_pv × age_pv)라 항상 12조합.
CREATE OR REPLACE VIEW v_meta_persona_insight_latest AS
SELECT
    m.id,
    m.dataset_id,
    m.category_id,
    m.category_name,
    a.period,
    a.gender,
    a.age,
    a.persona_index,
    a.gender_pv,
    a.age_pv
FROM meta_persona_insight m
LEFT JOIN LATERAL (
    SELECT p.period, p.gender, p.age, p.persona_index, p.gender_pv, p.age_pv
    FROM active_meta_persona_insight p
    WHERE p.meta_id = m.id
      AND p.gender IN ('m','f') AND p.age IN ('10','20','30','40','50','60')
      AND p.period = (
          SELECT max(p2.period) FROM active_meta_persona_insight p2
          WHERE p2.meta_id = m.id AND p2.gender IN ('m','f')
            AND p2.age IN ('10','20','30','40','50','60')
      )
) a ON true;


-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset_relation_canonical : 데이터셋 간 관계의 정본 (쌍+유형당 1행)
--
-- 출처: 협력기관 DDL 5(관계 method 확장). 모비젠 제안 우선순위를 그대로 구현한 것.
--   원본: 협력기관 수신본 5_관계_method_확장.sql
--
-- 배경: dcat_dataset_relation의 UNIQUE에 method가 들어가면서 같은 쌍·같은 유형에
--       산출 방법별로 행이 여러 개 존재하게 됐다. "A와 B는 의미적으로 유사한가"를
--       묻는 쪽은 그중 무엇을 답으로 삼을지 알 수 없다.
--       그 판단 규칙을 뷰로 고정해, 조회하는 쪽이 규칙을 몰라도 되게 한다.
--
-- 우선순위: APPROVED 우선 → score 최대 → created_at 최신
--
-- ※ 관계를 조회하는 코드는 dcat_dataset_relation이 아니라 이 뷰를 읽는다.
--   테이블을 직접 읽으면 같은 쌍이 method 수만큼 중복으로 나온다.
-- ═══════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS dcat_dataset_relation_canonical;

CREATE VIEW dcat_dataset_relation_canonical AS
SELECT DISTINCT ON (source_dataset_id, target_dataset_id, relation_type) *
FROM dcat_dataset_relation
ORDER BY source_dataset_id, target_dataset_id, relation_type,
         (status = 'APPROVED') DESC, score DESC, created_at DESC;
