-- ═══════════════════════════════════════════════════════════════
-- meta_news : Naver 뉴스 기사 단위 메타데이터 (Schema.org NewsArticle 기반)
-- dcat_dataset 1개에 N개의 기사 행이 연결됨
-- 같은 article_url이라도 dataset_id가 다르면 별도 행으로 관리
-- (동일 기사를 여러 데이터셋에서 독립적으로 추적하기 위함)
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_news CASCADE;

CREATE TABLE meta_news (

    -- ── 식별 ──────────────────────────────────────────────────
    id                  BIGSERIAL PRIMARY KEY,

    dataset_id          TEXT NOT NULL
                        REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,

    article_url         TEXT NOT NULL,
    -- schema:url | 언론사 원본 URL (Naver API: originallink)
    -- 기사 고유 식별자로 사용
    -- 예) 'https://www.yna.co.kr/view/AKR20260706000000017'

    UNIQUE (dataset_id, article_url),

    -- ── 기사 내용 (schema:NewsArticle) ───────────────────────
    title               TEXT NOT NULL,
    -- schema:headline | 제목 (<b> 태그 제거 후 저장)

    description         TEXT,
    -- schema:abstract | API 제공 요약/snippet (100~200자)
    -- <b> 태그 제거 후 저장

    content             TEXT,
    -- schema:articleBody | 스크래핑한 기사 본문 전체
    -- 스크래핑 실패 시 NULL

    has_content         BOOLEAN NOT NULL DEFAULT FALSE,
    -- 본문 스크래핑 성공 여부

    -- ── 출처 ──────────────────────────────────────────────────
    publisher           TEXT,
    -- schema:publisher | 언론사명 (예: '연합뉴스', 'YTN', '조선일보')
    -- 스크래핑 또는 URL 도메인에서 추출

    naver_url           TEXT,
    -- 네이버 리다이렉트 URL (Naver API: link)
    -- 예) 'https://news.naver.com/article/001/0015300000'

    published_at        TIMESTAMPTZ,
    -- schema:datePublished | 기사 발행일 (RFC 822 → TIMESTAMPTZ 변환)

    -- ── Naver 호스팅 여부 ─────────────────────────────────────
    is_naver_hosted     BOOLEAN NOT NULL DEFAULT FALSE,
    -- news.naver.com/article/{oid}/{aid} 형식으로 접근 가능한 기사 여부
    -- TRUE  → active_meta 댓글 수 수집 가능
    -- FALSE → 언론사 자체 서버 기사, 댓글 수 수집 불가

    naver_oid           TEXT,
    -- 네이버 언론사 코드 (is_naver_hosted=TRUE일 때만)
    -- 예) '001' = 연합뉴스, '023' = 조선일보, '056' = KBS

    naver_aid           TEXT,
    -- 네이버 기사 번호 (is_naver_hosted=TRUE일 때만)
    -- 예) '0015300000'

    -- ── 수집 맥락 ─────────────────────────────────────────────
    search_keyword      TEXT,
    -- 이 기사를 수집하게 된 검색 키워드
    -- 예) '인공지능', 'AI', '반도체'

    -- ── 관리 ──────────────────────────────────────────────────
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 본문 재스크래핑 등으로 필드 갱신 시 시각 (meta_video/meta_blog와 동일 패턴)

    is_removed           BOOLEAN NOT NULL DEFAULT FALSE,
    -- 정기 수집 시 검색 결과에서 더 이상 발견되지 않는 기사(비공개·삭제 등)에 TRUE.
    -- 행 자체는 지우지 않고 마지막 known 상태로 보존 (architecture/04_Collection_Pipeline_Operations.md 참조)

    removed_at            TIMESTAMPTZ
    -- is_removed가 TRUE로 바뀐 시각. is_removed=FALSE면 NULL
);

-- 조회용 인덱스
CREATE INDEX idx_meta_news_dataset    ON meta_news(dataset_id);
CREATE INDEX idx_meta_news_published  ON meta_news(published_at DESC);
CREATE INDEX idx_meta_news_publisher  ON meta_news(publisher);
CREATE INDEX idx_meta_news_hosted     ON meta_news(is_naver_hosted);
CREATE INDEX idx_meta_news_removed    ON meta_news(is_removed);
