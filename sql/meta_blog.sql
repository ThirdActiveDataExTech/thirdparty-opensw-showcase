-- ═══════════════════════════════════════════════════════════════
-- meta_blog : Naver 블로그 게시물 단위 메타데이터 (Schema.org BlogPosting 기반)
-- dcat_dataset 1개에 N개의 게시물 행이 연결됨
-- 같은 post_url이라도 dataset_id가 다르면 별도 행으로 관리
-- (동일 게시물을 여러 데이터셋에서 독립적으로 추적하기 위함)
--
-- Naver 블로그 검색 API(openapi.naver.com/v1/search/blog.json) 기준 필드.
-- meta_news와 동일한 패턴(article_url→post_url, has_content 등)을 따른다.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_blog CASCADE;

CREATE TABLE meta_blog (

    -- ── 식별 ──────────────────────────────────────────────────
    id                  BIGSERIAL PRIMARY KEY,

    dataset_id          TEXT NOT NULL
                        REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,

    post_url            TEXT NOT NULL,
    -- schema:url | 블로그 검색 API의 link 값 (예: 'https://blog.naver.com/{blogId}/{logNo}')
    -- 게시물 고유 식별자로 사용

    UNIQUE (dataset_id, post_url),

    -- ── 게시물 내용 (schema:BlogPosting) ─────────────────────
    title               TEXT NOT NULL,
    -- schema:headline | 제목 (<b> 태그 제거 후 저장)

    description         TEXT,
    -- schema:abstract | API 제공 요약/snippet
    -- <b> 태그 제거 후 저장

    content             TEXT,
    -- schema:articleBody | 스크래핑한 게시물 본문 전체
    -- 스크래핑 실패 시 NULL

    has_content         BOOLEAN NOT NULL DEFAULT FALSE,
    -- 본문 스크래핑 성공 여부

    -- ── 작성자 ────────────────────────────────────────────────
    blogger_name        TEXT,
    -- schema:author.name | 블로그 이름 (API: bloggername)

    blogger_link         TEXT,
    -- 블로그 홈 URL (API: bloggerlink)

    -- ── 호스팅 플랫폼 ─────────────────────────────────────────
    platform             TEXT NOT NULL,
    -- post_url의 host에서 파싱해 채움. Naver 블로그 검색 API(Blog Search)는
    -- blog.naver.com 외에도 검색 결과에 노출되는 티스토리/브런치/워드프레스/Blogger 등
    -- 다양한 플랫폼을 함께 반환하기 때문에 필요 (API 이름이 "Naver Blog Search"가 아님)
    -- 값 예시: 'naver', 'tistory', 'brunch', 'wordpress', 'blogger', 'other'
    -- 실측(2026-07-24, ADR-006 조사 중): 다양한 검색어 350건 샘플에서 blog.naver.com 96%,
    -- tistory.com 3.4%, 완전 커스텀 도메인 소수 — brunch/wordpress/blogger는 이번 샘플엔
    -- 없었으나 다른 검색어에서 나올 수 있어 enum 제약은 걸지 않음
    -- 아래 blog_id/log_no, active_meta 반응 수 수집(ADR-006 결정: 반응만 수집, 댓글/조회수는
    -- 미수집)은 platform='naver'일 때만 해당

    -- ── Naver 블로그 ID 파싱값 (platform='naver'일 때만 채움) ────
    -- 반응(공감 등) 수 수집의 키 — ADR-006으로 확정, active_meta_blog 연동 완료
    blog_id              TEXT,
    -- 네이버 블로그 ID (예: 'techblog_samsung')

    log_no               TEXT,
    -- 게시물 번호 (예: '223456789')

    published_at        TIMESTAMPTZ,
    -- schema:datePublished | 게시일 (API postdate 'YYYYMMDD' → TIMESTAMPTZ 변환)

    -- ── 수집 맥락 ─────────────────────────────────────────────
    search_keyword      TEXT,
    -- 이 게시물을 수집하게 된 검색 키워드
    -- 예) '인공지능', 'AI', '반도체'

    -- ── 관리 ──────────────────────────────────────────────────
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 본문 재스크래핑 등으로 필드 갱신 시 시각

    is_removed            BOOLEAN NOT NULL DEFAULT FALSE,
    -- 정기 수집 시 검색 결과에서 더 이상 발견되지 않는 게시물(비공개·삭제 등)에 TRUE.
    -- 행 자체는 지우지 않고 마지막 known 상태로 보존 (architecture/04_Collection_Pipeline_Operations.md 참조)

    removed_at             TIMESTAMPTZ
    -- is_removed가 TRUE로 바뀐 시각. is_removed=FALSE면 NULL
);

-- 조회용 인덱스
CREATE INDEX idx_meta_blog_dataset    ON meta_blog(dataset_id);
CREATE INDEX idx_meta_blog_published  ON meta_blog(published_at DESC);
CREATE INDEX idx_meta_blog_blogger    ON meta_blog(blog_id);
CREATE INDEX idx_meta_blog_removed    ON meta_blog(is_removed);
CREATE INDEX idx_meta_blog_platform   ON meta_blog(platform);
