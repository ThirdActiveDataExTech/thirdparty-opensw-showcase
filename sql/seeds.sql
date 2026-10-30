-- ═══════════════════════════════════════════════════════════════
-- seeds.sql : 샘플 데이터 (개발/테스트용)
-- 실행 전 DDL이 모두 적용돼 있어야 함
-- 실행 순서:
--   dcat_dataset → dcat_provenance → data_registry → dcat_dataset_vec
--   → meta_video → active_meta_video → meta_video_vec
--   → meta_news → active_meta_news
--   → meta_shopping_insight → active_meta_shopping_insight
--   → meta_persona_insight → active_meta_persona_insight
--   → meta_blog → active_meta_blog (ADR-006 확정 — 반응 수만 수집)
--
-- dataset_credentials는 의도적으로 여기서 시드하지 않는다: 암호화 키(ENCRYPTION_KEY)를
-- K8s Secret(dataset-credentials-encryption-key)에서만 가져오게 설계했고, 그 키를 이런
-- 정적 SQL 파일에 리터럴로 박아넣지 않기로 했다(sql/dataset_credentials.sql 헤더 참조).
-- Secret이 실제로 생성되고 ENCRYPTION_KEY가 .env에 채워진 뒤, 애플리케이션 코드(파라미터
-- 바인딩)로 예시 행을 넣는다.
-- ═══════════════════════════════════════════════════════════════

-- ── dcat_dataset ──────────────────────────────────────────────

INSERT INTO dcat_dataset (
    dataset_id, title, description,
    publisher, source, source_type, landing_page, access_url, subjects,
    language, spatial, temporal_start, temporal_end,
    temporal_resolution, accrual_periodicity, item_count,
    keywords, license, rights,
    dataset_origin, owner_id, visibility, external_ids
) VALUES
(
    'urn:naver:shopping_insight',
    '네이버 쇼핑 인사이트 카테고리 수집',
    '성별×연령(12조합) 필터로 수집한 카테고리별 일간 검색량 지수. anchor 보정(intra_scale) 및 inter_scale 적용.',
    'Naver', 'Naver', 'shopping_insight',
    'https://datalab.naver.com/shopping/',
    'https://openapi.naver.com/v1/datalab/shopping/categories',
    '["50000148","50001828","50001421","50000204","50000167"]',
    'ko', 'KR', '2025-06-17', '2026-06-16', 'P1D', 'P1D', 5,
    '["쇼핑","검색량","카테고리","성별","연령","네이버"]',
    'https://developers.naver.com/notice/terms',
    '네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.',
    'admin', NULL, 'ORG', '["naver:shopping_insight:sha256-07d4a7019a1c"]'
),
(
    'urn:naver:persona_insight',
    '네이버 쇼핑 인사이트 페르소나 분석',
    '카테고리별 성별·연령 독립 가정 기반 persona_index 산출. gender_pv × age_pv 교차 추정.',
    'Naver', 'Naver', 'persona_insight',
    'https://datalab.naver.com/shopping/',
    'https://openapi.naver.com/v1/datalab/shopping/category/gender,age',
    '["50000148","50001828","50001421","50000204"]',
    'ko', 'KR', '2025-06-18', '2026-06-17', 'P1D', 'P1D', 4,
    '["쇼핑","페르소나","성별","연령","카테고리"]',
    'https://developers.naver.com/notice/terms',
    '네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.',
    'admin', NULL, 'ORG', '["naver:persona_insight:sha256-0d08a424c296"]'
),
(
    'urn:youtube:samsung_official',
    '삼성전자 공식 유튜브 채널',
    '삼성전자 공식 YouTube 채널(@Samsung) 전체 영상 메타데이터 수집. 주간 단위 업데이트.',
    'YouTube', 'YouTube', 'video',
    'https://www.youtube.com/@Samsung',
    'https://www.googleapis.com/youtube/v3/videos',
    '["UCWwgaK7x0_FR1goeSRazfsQ"]',
    'ko', 'KR', '2024-01-01', NULL, NULL, 'P7D', 3,
    '["유튜브","삼성전자","테크","채널"]',
    'https://developers.google.com/youtube/terms/api-services-tos',
    'YouTube API Services Terms of Service 준수. 수집 데이터의 제3자 제공 시 Google 사전 승인 필요.',
    'admin', NULL, 'ORG', '["youtube:UCWwgaK7x0_FR1goeSRazfsQ"]'
),
(
    'urn:naver:news_ai',
    '네이버 뉴스 AI 관련 기사 수집',
    '네이버 뉴스 API를 통해 인공지능 관련 키워드로 수집한 뉴스 기사. 본문 스크래핑 포함.',
    'Naver', 'Naver', 'news',
    'https://news.naver.com',
    'https://openapi.naver.com/v1/search/news.json',
    '["인공지능","AI","머신러닝","딥러닝"]',
    'ko', 'KR', '2026-01-01', NULL, NULL, 'P1D', 3,
    '["뉴스","AI","인공지능","네이버"]',
    'https://developers.naver.com/notice/terms',
    '네이버 API 이용약관 준수. 뉴스 본문 스크래핑은 각 언론사 저작권 정책 별도 확인 필요.',
    'admin', NULL, 'ORG', '["naver:news:sha256-3c639c929baf"]'
),
-- user 생성 예시: YouTube 채널 2개에서 HBM 관련 영상만 직접 선택한 사용자 정의 데이터셋
-- owner_id는 예시값 — 실제 계정 테이블이 아직 없어 임의 문자열 (§10/2-6 참조)
(
    'urn:youtube:hbm_video_collection',
    'HBM 관련 영상 모음',
    '삼성전자·SK하이닉스 채널에서 HBM(High Bandwidth Memory) 관련 영상을 직접 선택해 구성한 사용자 정의 데이터셋.',
    'YouTube', 'YouTube', 'video',
    NULL, NULL,
    '["UCWwgaK7x0_FR1goeSRazfsQ","UCltyil2FaQZZ4kUNinKkKmw"]',
    'ko', 'KR', NULL, NULL, NULL, NULL, 1,
    '["HBM","반도체","삼성전자","SK하이닉스"]',
    'https://developers.google.com/youtube/terms/api-services-tos',
    'YouTube API Services Terms of Service 준수.',
    'user', 'demo-user-0001', 'ORG', '["youtube:UCWwgaK7x0_FR1goeSRazfsQ","youtube:UCltyil2FaQZZ4kUNinKkKmw"]'
),
(
    'urn:naver:blog_ai',
    '네이버 블로그 AI·반도체 관련 게시물 수집',
    '네이버 블로그 검색 API를 통해 AI/반도체 관련 키워드로 수집한 블로그 게시물. 본문 스크래핑 포함.',
    'Naver', 'Naver', 'blog',
    'https://section.blog.naver.com/',
    'https://openapi.naver.com/v1/search/blog.json',
    '["인공지능","AI","반도체","HBM"]',
    'ko', 'KR', '2026-06-20', NULL, NULL, 'P1D', 3,
    '["블로그","AI","반도체","네이버"]',
    'https://developers.naver.com/notice/terms',
    '네이버 API 이용약관 준수. 블로그 본문 스크래핑은 저작권 정책 별도 확인 필요. active_meta_blog는 ADR-006으로 반응 수 수집 확정(댓글 수·조회수는 미수집).',
    'admin', NULL, 'ORG', '["naver:blog:sha256-b3fa704db4e7"]'
);

-- ── dcat_provenance ───────────────────────────────────────────

INSERT INTO dcat_provenance (
    dataset_id, activity_type, agent, triggered_by,
    started_at, ended_at, status, rows_affected, params, error_message, notes
) VALUES
(
    'urn:naver:shopping_insight', 'initial', 'urn:naver:shopping_insight', 'manual',
    '2025-06-18 02:00:00+09', '2025-06-18 02:04:31+09', 'success', 4732,
    '{"phase":"1/2","start_date":"2024-06-18","end_date":"2025-06-17"}',
    NULL, '최초 실행 1단계: 1년치 소급 수집'
),
(
    'urn:naver:shopping_insight', 'initial', 'urn:naver:shopping_insight', 'manual',
    '2025-06-18 02:04:31+09', '2025-06-18 02:05:58+09', 'success', 364,
    '{"phase":"2/2","start_date":"2025-05-21","end_date":"2025-06-17"}',
    NULL, '최초 실행 2단계: 28일 overlap 수집'
),
(
    'urn:naver:shopping_insight', 'update', 'urn:naver:shopping_insight',
    'K8s CronJob naver-shopping-cronjob',
    '2025-06-25 02:00:00+09', '2025-06-25 02:01:12+09', 'success', 91,
    '{"start_date":"2025-05-28","end_date":"2025-06-24","overlap_days":28}',
    NULL, NULL
),
(
    'urn:naver:shopping_insight', 'update', 'urn:naver:shopping_insight',
    'K8s CronJob naver-shopping-cronjob',
    '2026-06-30 02:00:00+09', '2026-06-30 02:01:09+09', 'success', 91,
    '{"start_date":"2026-06-02","end_date":"2026-06-29","overlap_days":28}',
    NULL, NULL
),
(
    'urn:naver:persona_insight', 'initial', 'naver_persona', 'manual',
    '2025-06-18 03:00:00+09', '2025-06-18 03:12:44+09', 'success', 56784,
    '{"start_date":"2025-06-18","end_date":"2026-06-17"}',
    NULL, '최초 실행: gender×age 12조합 전체'
),
(
    'urn:naver:persona_insight', 'update', 'naver_persona',
    'K8s CronJob naver-persona-cronjob',
    '2026-06-30 03:00:00+09', '2026-06-30 03:02:31+09', 'success', 1092,
    '{"start_date":"2026-06-23","end_date":"2026-06-29","overlap_days":28}',
    NULL, NULL
),
(
    'urn:youtube:samsung_official', 'initial', 'youtube_collector', 'manual',
    '2026-06-30 04:00:00+09', '2026-06-30 04:03:21+09', 'success', 3,
    '{"channel_id":"UCWwgaK7x0_FR1goeSRazfsQ","max_results":500}',
    NULL, '채널 전체 영상 최초 수집 (샘플 3건)'
),
(
    'urn:naver:news_ai', 'initial', 'naver_news', 'manual',
    '2026-01-01 06:00:00+09', '2026-01-01 06:00:47+09', 'success', 1200,
    '{"keywords":["인공지능","AI","머신러닝"],"display":100}',
    NULL, '최초 수집'
),
(
    'urn:naver:news_ai', 'update', 'naver_news',
    'K8s CronJob naver-news-cronjob',
    '2026-06-30 06:00:00+09', '2026-06-30 06:00:12+09', 'failure', 0,
    '{"keywords":["인공지능","AI"],"display":100}',
    'HTTP 429 Too Many Requests: API 일일 호출 한도 초과', NULL
),
(
    'urn:naver:blog_ai', 'initial', 'naver_blog', 'manual',
    '2026-06-28 07:00:00+09', '2026-06-28 07:00:33+09', 'success', 3,
    '{"keywords":["인공지능","AI","반도체"],"display":30}',
    NULL, '최초 수집 (샘플 3건, active_meta 파이프라인은 ADR-006으로 반응 수 수집 확정)'
);

-- ── data_registry ─────────────────────────────────────────────

INSERT INTO data_registry (
    dataset_id,
    s3_raw_prefix, s3_jsonld_prefix,
    pg_meta_table, pg_active_table, vec_collection,
    status, last_collected_at, next_collect_at, last_error,
    item_count, row_count, temporal_start, temporal_end
) VALUES
(
    'urn:naver:shopping_insight',
    'raw/shopping_insight/naver_shopping_insight/', 'jsonld/shopping_insight/naver_shopping_insight/',
    'meta_shopping_insight', 'active_meta_shopping_insight', 'dcat_dataset_vec',
    'active', '2026-06-30 02:01:09+09', '2026-07-01 02:00:00+09', NULL,
    5, 5278, '2025-06-17', '2026-06-16'
    -- item_count=5: 이 데이터셋이 추적하는 카테고리 수 (anchor 포함, meta_shopping_insight 행 수)
),
(
    'urn:naver:persona_insight',
    'raw/persona_insight/naver_persona_insight/', 'jsonld/persona_insight/naver_persona_insight/',
    'meta_persona_insight', 'active_meta_persona_insight', 'dcat_dataset_vec',
    'active', '2026-06-30 03:02:31+09', '2026-07-01 03:00:00+09', NULL,
    4, 57876, '2025-06-18', '2026-06-17'
),
(
    'urn:youtube:samsung_official',
    'raw/video/youtube_samsung_official/', 'jsonld/video/youtube_samsung_official/',
    'meta_video', 'active_meta_video', 'dcat_dataset_vec',
    'active', '2026-06-30 04:03:21+09', '2026-07-07 04:00:00+09', NULL,
    3, 3, '2024-01-01', NULL
    -- item_count=3: 채널 영상 3편. row_count는 최초 수집 시점(3건) 기준 —
    -- 07-07 2차 수집 이후 active_meta_video는 6행이지만 대응하는
    -- dcat_provenance 'update' 기록이 없어 아직 갱신 전 (기존 시드 데이터의 기존 격차, 오늘 범위 아님)
),
(
    'urn:naver:news_ai',
    'raw/news/naver_news_ai/', 'jsonld/news/naver_news_ai/',
    'meta_news', 'active_meta_news', 'dcat_dataset_vec',
    'error', '2026-01-01 06:00:47+09', '2026-07-01 06:00:00+09',
    'HTTP 429 Too Many Requests: API 일일 호출 한도 초과',
    3, 1200, '2026-01-01', NULL
    -- item_count=3: 수집된 기사 3건 (meta_news 행 수)
),
(
    'urn:youtube:hbm_video_collection',
    NULL, NULL,
    'meta_video', 'active_meta_video', 'dcat_dataset_vec',
    'pending', NULL, NULL, NULL,
    1, 0, NULL, NULL
    -- item_count=1: yt_vid_002 1편만 직접 선택
),
(
    'urn:naver:blog_ai',
    'raw/blog/naver_blog_ai/', 'jsonld/blog/naver_blog_ai/',
    'meta_blog', 'active_meta_blog', 'dcat_dataset_vec',
    'active', '2026-06-28 07:00:33+09', '2026-07-01 07:00:00+09', NULL,
    3, 3, '2026-06-20', NULL
    -- item_count=3: 게시물 3건. active_meta_blog는 ADR-006으로 반응 수 수집 확정,
    -- row_count도 현재 active_meta 시드 행 수(3)와 동일
);

-- ── dcat_dataset_vec ──────────────────────────────────────────
-- 임베딩은 scripts/embed_datasets.py 로 생성
-- seeds.sql 실행 후 아래 명령어로 임베딩 삽입:
--   python scripts/embed_datasets.py

-- ── meta_video ────────────────────────────────────────

INSERT INTO meta_video (
    dataset_id, video_id,
    title, description, published_at,
    channel_id, channel_title,
    tags, category_id,
    duration, duration_seconds,
    definition, default_language, default_audio_language,
    has_caption, thumbnail_url,
    initial_view_count, initial_like_count, initial_comment_count
) VALUES
-- urn:youtube:samsung_official 채널 영상 3건
(
    'urn:youtube:samsung_official',
    'yt_vid_001',
    'Samsung Galaxy S25 Ultra | Official Introduction',
    '삼성전자 갤럭시 S25 Ultra 공식 소개 영상. 새로운 AI 기능과 카메라 성능 업그레이드를 담았습니다.',
    '2025-01-22 10:00:00+09',
    'UCWwgaK7x0_FR1goeSRazfsQ', 'Samsung',
    '["Galaxy","S25","Ultra","Samsung","갤럭시","스마트폰"]',
    '28',
    'PT3M42S', 222,
    'hd', 'ko', 'ko',
    TRUE, 'https://i.ytimg.com/vi/yt_vid_001/maxresdefault.jpg',
    15230000, 98000, 4200
),
(
    'urn:youtube:samsung_official',
    'yt_vid_002',
    'Samsung HBM3E | 12단 적층 기술 소개',
    '삼성전자 HBM3E 12단 적층 D램의 기술 개요. AI 서버용 고성능 메모리 솔루션.',
    '2024-08-15 14:00:00+09',
    'UCWwgaK7x0_FR1goeSRazfsQ', 'Samsung',
    '["HBM","HBM3E","반도체","메모리","AI","데이터센터"]',
    '28',
    'PT5M17S', 317,
    'hd', 'ko', 'ko',
    TRUE, 'https://i.ytimg.com/vi/yt_vid_002/maxresdefault.jpg',
    3820000, 41000, 890
),
(
    'urn:youtube:samsung_official',
    'yt_vid_003',
    'Galaxy AI | 2025 AI 기능 완벽 정리',
    '갤럭시 AI의 2025년 주요 기능을 한눈에 정리. 실시간 통역, 서클 투 서치 등 핵심 AI 기능 시연.',
    '2025-03-10 10:00:00+09',
    'UCWwgaK7x0_FR1goeSRazfsQ', 'Samsung',
    '["Galaxy AI","AI","갤럭시","인공지능","서클투서치"]',
    '28',
    'PT7M05S', 425,
    'hd', 'ko', 'ko',
    TRUE, 'https://i.ytimg.com/vi/yt_vid_003/maxresdefault.jpg',
    8940000, 67000, 2100
),
-- urn:youtube:hbm_video_collection: yt_vid_002는 위와 동일한 영상이지만 별도 데이터셋으로 추적
(
    'urn:youtube:hbm_video_collection',
    'yt_vid_002',
    'Samsung HBM3E | 12단 적층 기술 소개',
    '삼성전자 HBM3E 12단 적층 D램의 기술 개요. AI 서버용 고성능 메모리 솔루션.',
    '2024-08-15 14:00:00+09',
    'UCWwgaK7x0_FR1goeSRazfsQ', 'Samsung',
    '["HBM","HBM3E","반도체","메모리","AI","데이터센터"]',
    '28',
    'PT5M17S', 317,
    'hd', 'ko', 'ko',
    TRUE, 'https://i.ytimg.com/vi/yt_vid_002/maxresdefault.jpg',
    3820000, 41000, 890
);

-- ── active_meta_video ───────────────────────────────────────
-- meta_video.id 는 BIGSERIAL이라 삽입 순서대로 1,2,3,4 가 됨
-- 1 = urn:youtube:samsung_official / yt_vid_001
-- 2 = urn:youtube:samsung_official / yt_vid_002
-- 3 = urn:youtube:samsung_official / yt_vid_003
-- 4 = urn:youtube:hbm_video_collection / yt_vid_002

INSERT INTO active_meta_video (
    meta_id, collected_at,
    view_count, like_count, comment_count,
    delta_views, delta_likes, delta_comments
) VALUES
-- meta_id=1 (samsung_official / yt_vid_001): 2회 수집
(1, '2026-06-30 04:03:21+09',  15230000, 98000, 4200,   NULL,  NULL,  NULL),
(1, '2026-07-07 04:01:44+09',  15410000, 99200, 4350,  180000,  1200,   150),
-- meta_id=2 (samsung_official / yt_vid_002): 2회 수집
(2, '2026-06-30 04:03:21+09',   3820000, 41000,  890,   NULL,  NULL,  NULL),
(2, '2026-07-07 04:01:44+09',   3851000, 41300,  910,   31000,   300,    20),
-- meta_id=3 (samsung_official / yt_vid_003): 2회 수집
(3, '2026-06-30 04:03:21+09',   8940000, 67000, 2100,   NULL,  NULL,  NULL),
(3, '2026-07-07 04:01:44+09',   9020000, 67800, 2180,   80000,   800,    80),
-- meta_id=4 (user_hbm / yt_vid_002): 이 데이터셋은 07-06에 추가됨 → 수집 타임라인 독립
(4, '2026-07-06 10:00:00+09',   3848000, 41280,  908,   NULL,  NULL,  NULL);

-- ── meta_news ───────────────────────────────────────────

INSERT INTO meta_news (
    dataset_id, article_url,
    title, description, content, has_content,
    publisher, naver_url, published_at,
    is_naver_hosted, naver_oid, naver_aid,
    search_keyword
) VALUES
-- Naver 호스팅 기사 (댓글 수집 가능)
(
    'urn:naver:news_ai',
    'https://www.yna.co.kr/view/AKR20260704000000017',
    '삼성전자, 차세대 AI 반도체 HBM4 개발 본격화',
    '삼성전자가 엔비디아 차세대 AI 가속기에 탑재될 HBM4(High Bandwidth Memory 4) 개발을 본격화했다고 밝혔다.',
    '삼성전자는 4일 차세대 AI 반도체 메모리인 HBM4 개발에 착수했다고 발표했다. HBM4는 기존 HBM3E 대비 대역폭이 2배 이상 향상되며 전력 효율도 크게 개선될 것으로 기대된다. 삼성전자 관계자는 "2027년 양산을 목표로 개발 중"이라고 밝혔다.',
    TRUE,
    '연합뉴스',
    'https://news.naver.com/article/001/0015300001',
    '2026-07-04 10:30:00+09',
    TRUE, '001', '0015300001',
    '인공지능'
),
-- Naver 호스팅 기사 (댓글 수집 가능)
(
    'urn:naver:news_ai',
    'https://biz.chosun.com/it-science/ict/2026/07/03/ai-data-center',
    'AI 데이터센터 전력 수요 급증... 2030년 국내 전력 소비의 15% 차지',
    'AI 데이터센터의 폭발적인 성장으로 전력 수요가 급증하고 있으며 2030년에는 국내 전체 전력 소비의 15%를 차지할 것으로 전망된다.',
    '인공지능(AI) 기술이 급속도로 발전하면서 AI 데이터센터의 전력 소비가 급증하고 있다. 한국전력공사에 따르면 2030년 AI 데이터센터의 전력 소비량은 현재의 5배에 달할 것으로 예측된다. 이에 따라 신재생에너지 확충과 전력망 고도화가 시급한 과제로 떠올랐다.',
    TRUE,
    '조선비즈',
    'https://news.naver.com/article/023/0003878001',
    '2026-07-03 14:00:00+09',
    TRUE, '023', '0003878001',
    'AI'
),
-- 외부 기사 (댓글 수집 불가 — is_naver_hosted=FALSE)
(
    'urn:naver:news_ai',
    'https://www.sedaily.com/NewsView/2DABCDEF12',
    '머신러닝 모델 경량화 기술 동향... 온디바이스 AI 시대 가속',
    '온디바이스 AI 구현을 위한 머신러닝 모델 경량화 기술이 빠르게 발전하고 있다.',
    '스마트폰·IoT 기기에서 AI를 직접 구동하는 온디바이스 AI 시대가 가속화되면서 모델 경량화 기술이 주목받고 있다. 양자화(Quantization), 지식 증류(Knowledge Distillation), 가지치기(Pruning) 등 다양한 기법이 발전하며 대형 AI 모델을 소형 기기에서도 구동할 수 있게 됐다.',
    TRUE,
    '서울경제',
    NULL,
    '2026-07-02 09:00:00+09',
    FALSE, NULL, NULL,
    '머신러닝'
);

-- ── active_meta_news ────────────────────────────────────
-- meta_news.id 는 BIGSERIAL이라 삽입 순서대로 1,2,3 이 됨
-- 1 = urn:naver:news_ai / 연합뉴스 HBM4 기사 (Naver 호스팅)
-- 2 = urn:naver:news_ai / 조선비즈 데이터센터 기사 (Naver 호스팅)
-- 3 = urn:naver:news_ai / 서울경제 경량화 기사 (외부 기사 — 행 없음)

INSERT INTO active_meta_news (
    meta_id, collected_at,
    comment_count, expose_count, reply_count,
    delta_comments
) VALUES
-- meta_id=1 (연합뉴스 HBM4): 2회 수집
(1, '2026-07-04 11:00:00+09',  28,  25,  3,  NULL),
(1, '2026-07-06 11:00:00+09',  42,  40,  8,    14),
-- meta_id=2 (조선비즈 데이터센터): 2회 수집
(2, '2026-07-03 15:00:00+09',   8,   8,  0,  NULL),
(2, '2026-07-06 11:00:00+09',  15,  14,  2,     7);
-- meta_id=3 (서울경제 외부 기사): is_naver_hosted=FALSE → 행 없음

-- ── meta_shopping_insight ───────────────────────────────────────
-- urn:naver:shopping_insight 데이터셋의 카테고리 정보
-- anchor: 패션의류 (50000148) — 모든 배치에 포함되는 기준 카테고리

INSERT INTO meta_shopping_insight (
    dataset_id, category_id, category_name,
    cat_level1, cat_level2, cat_level3, cat_level4,
    is_anchor
) VALUES
('urn:naver:shopping_insight', '50000148', '패션의류',           '패션의류', NULL,     NULL,    NULL,  TRUE),
('urn:naver:shopping_insight', '50001828', '패션의류>남성의류',   '패션의류', '남성의류', NULL,   NULL,  FALSE),
('urn:naver:shopping_insight', '50001421', '패션의류>여성의류',   '패션의류', '여성의류', NULL,   NULL,  FALSE),
('urn:naver:shopping_insight', '50000204', '패션잡화',           '패션잡화', NULL,     NULL,    NULL,  FALSE),
('urn:naver:shopping_insight', '50000167', '스포츠/레저',        '스포츠/레저', NULL,   NULL,    NULL,  FALSE);

-- ── active_meta_shopping_insight ────────────────────────────────
-- meta_shopping_insight.id 삽입 순서: 1=패션의류(anchor), 2=남성의류, 3=여성의류, 4=패션잡화, 5=스포츠/레저
-- 성별·연령 조합 샘플: 전체('') × 전체('') 1조합만 예시로 삽입

INSERT INTO active_meta_shopping_insight (
    meta_id, period, gender, age,
    raw_ratio, anchor_raw_ratio, normalized_ratio,
    scale_factor, pseudo_volume,
    batch_index, collected_at
) VALUES
-- 2026-06-30 수집 (첫 수집 → scale_factor=1.0, delta 없음)
-- anchor(패션의류): normalized=100.0 고정
(1, '2026-06-30', '', '', 100.0, 100.0, 100.0, 1.0, 100.0, 0, '2026-06-30 02:01:09+09'),
(2, '2026-06-30', '', '',  38.2, 100.0,  38.2, 1.0,  38.2, 0, '2026-06-30 02:01:09+09'),
(3, '2026-06-30', '', '',  52.7, 100.0,  52.7, 1.0,  52.7, 0, '2026-06-30 02:01:09+09'),
(4, '2026-06-30', '', '',  21.4, 100.0,  21.4, 1.0,  21.4, 1, '2026-06-30 02:01:09+09'),
(5, '2026-06-30', '', '',  15.9, 100.0,  15.9, 1.0,  15.9, 1, '2026-06-30 02:01:09+09'),
-- 2026-07-07 수집 (두 번째 → inter_scale 적용)
(1, '2026-07-07', '', '', 100.0, 100.0, 100.0, 1.0123, 101.23, 0, '2026-07-07 02:00:51+09'),
(2, '2026-07-07', '', '',  39.8, 100.0,  39.8, 1.0123,  40.29, 0, '2026-07-07 02:00:51+09'),
(3, '2026-07-07', '', '',  51.1, 100.0,  51.1, 1.0123,  51.73, 0, '2026-07-07 02:00:51+09'),
(4, '2026-07-07', '', '',  22.0, 100.0,  22.0, 1.0123,  22.27, 1, '2026-07-07 02:00:51+09'),
(5, '2026-07-07', '', '',  16.3, 100.0,  16.3, 1.0123,  16.50, 1, '2026-07-07 02:00:51+09');

-- ── meta_persona_insight ────────────────────────────────────────
-- urn:naver:persona_insight 데이터셋의 카테고리 정보 (anchor 개념 없음)

INSERT INTO meta_persona_insight (
    dataset_id, category_id, category_name,
    cat_level1, cat_level2, cat_level3, cat_level4
) VALUES
('urn:naver:persona_insight', '50000148', '패션의류',         '패션의류', NULL,     NULL, NULL),
('urn:naver:persona_insight', '50001828', '패션의류>남성의류', '패션의류', '남성의류', NULL, NULL),
('urn:naver:persona_insight', '50001421', '패션의류>여성의류', '패션의류', '여성의류', NULL, NULL),
('urn:naver:persona_insight', '50000204', '패션잡화',         '패션잡화', NULL,     NULL, NULL);

-- ── active_meta_persona_insight ─────────────────────────────────
-- meta_persona_insight.id 삽입 순서: 1=패션의류, 2=남성의류, 3=여성의류, 4=패션잡화
-- 샘플: meta_id=1(패션의류) × 2일 × 2성별 × 2연령(20대·30대) = 8행

INSERT INTO active_meta_persona_insight (
    meta_id, period, gender, age,
    gender_ratio, age_ratio,
    gender_scale, age_scale,
    gender_pv, age_pv, persona_index,
    collected_at
) VALUES
-- 2026-06-30 수집 (첫 수집 → scale=1.0)
(1, '2026-06-30', 'm', '20', 42.1, 28.3, 1.0, 1.0, 42.1, 28.3, 1191.43, '2026-06-30 03:02:31+09'),
(1, '2026-06-30', 'm', '30', 42.1, 35.7, 1.0, 1.0, 42.1, 35.7, 1502.97, '2026-06-30 03:02:31+09'),
(1, '2026-06-30', 'f', '20', 58.3, 28.3, 1.0, 1.0, 58.3, 28.3, 1649.89, '2026-06-30 03:02:31+09'),
(1, '2026-06-30', 'f', '30', 58.3, 35.7, 1.0, 1.0, 58.3, 35.7, 2081.31, '2026-06-30 03:02:31+09'),
-- 2026-07-07 수집 (두 번째 → scale 적용)
(1, '2026-07-07', 'm', '20', 43.5, 29.1, 1.0089, 1.0042, 43.89, 29.22, 1281.86, '2026-07-07 03:01:14+09'),
(1, '2026-07-07', 'm', '30', 43.5, 36.2, 1.0089, 1.0042, 43.89, 36.35, 1595.39, '2026-07-07 03:01:14+09'),
(1, '2026-07-07', 'f', '20', 57.8, 29.1, 1.0089, 1.0042, 58.31, 29.22, 1703.81, '2026-07-07 03:01:14+09'),
(1, '2026-07-07', 'f', '30', 57.8, 36.2, 1.0089, 1.0042, 58.31, 36.35, 2119.57, '2026-07-07 03:01:14+09');

-- ── meta_blog ───────────────────────────────────────────
-- urn:naver:blog_ai 데이터셋의 게시물 3건 (본문 스크래핑 실패 1건 포함)

INSERT INTO meta_blog (
    dataset_id, post_url,
    title, description, content, has_content,
    blogger_name, blogger_link,
    platform, blog_id, log_no,
    published_at, search_keyword
) VALUES
-- 본문 스크래핑 성공
(
    'urn:naver:blog_ai',
    'https://blog.naver.com/techinsight_kr/223456781',
    'HBM4 이란 무엇인가 - 차세대 메모리 완벽 정리',
    '삼성전자와 SK하이닉스가 개발 중인 HBM4에 대해 알기 쉽게 정리해봤습니다. HBM3E와의 차이점부터 양산 일정까지.',
    'HBM(High Bandwidth Memory)은 여러 D램을 수직으로 적층해 대역폭을 크게 늘린 메모리입니다. HBM4는 기존 HBM3E 대비 대역폭이 2배 이상 향상될 것으로 예상되며, 삼성전자와 SK하이닉스 모두 2027년 양산을 목표로 개발 중입니다. 이번 글에서는 HBM4가 왜 AI 반도체에 필수적인지, 그리고 각 제조사의 기술 경쟁 구도를 정리합니다.',
    TRUE,
    '테크인사이트', 'https://blog.naver.com/techinsight_kr',
    'naver', 'techinsight_kr', '223456781',
    '2026-06-20 14:30:00+09', 'HBM4'
),
-- 본문 스크래핑 성공
(
    'urn:naver:blog_ai',
    'https://blog.naver.com/galaxy_review/223456912',
    '갤럭시 S25 울트라 AI 기능 3주 사용 후기',
    '갤럭시 S25 울트라를 3주간 사용하면서 느낀 AI 기능들을 솔직하게 리뷰합니다.',
    '실시간 통역 기능은 해외여행에서 특히 유용했습니다. 서클 투 서치는 검색 편의성을 크게 높여줬고요. 다만 배터리 소모가 AI 기능을 켰을 때 눈에 띄게 늘어나는 점은 아쉬웠습니다. 종합적으로는 만족스러운 업그레이드였습니다.',
    TRUE,
    '갤럭시리뷰어', 'https://blog.naver.com/galaxy_review',
    'naver', 'galaxy_review', '223456912',
    '2026-06-25 09:15:00+09', 'Galaxy AI'
),
-- 본문 스크래핑 실패 (has_content=FALSE)
(
    'urn:naver:blog_ai',
    'https://blog.naver.com/semicon_daily/223457033',
    '2026년 반도체 업계 하반기 전망',
    'AI 반도체 수요 증가와 함께 메모리 업계가 어떻게 움직이고 있는지 정리했습니다.',
    NULL,
    FALSE,
    '반도체데일리', 'https://blog.naver.com/semicon_daily',
    'naver', 'semicon_daily', '223457033',
    '2026-06-28 18:00:00+09', '반도체 전망'
);

-- ── active_meta_blog ────────────────────────────────────
-- ADR-006으로 확정된 스키마 — 반응(공감 등) 수만 수집 (댓글 수·조회수는 미수집).
-- meta_blog.id 삽입 순서: 1=HBM4, 2=Galaxy AI, 3=반도체 전망(본문 없음, 행 없음)

INSERT INTO active_meta_blog (
    meta_id, collected_at,
    reaction_count, reaction_breakdown,
    delta_reactions
) VALUES
-- meta_id=1 (HBM4): 2회 수집
(1, '2026-06-30 07:00:33+09', 34, '{"like": 34}'::jsonb,                    NULL),
(1, '2026-07-07 07:00:18+09', 51, '{"like": 48, "impressive": 3}'::jsonb,      17),
-- meta_id=2 (Galaxy AI): 1회 수집
(2, '2026-06-30 07:00:33+09', 22, '{"like": 22}'::jsonb,                    NULL);
