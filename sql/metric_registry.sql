-- ═══════════════════════════════════════════════════════════════
-- metric_registry : 지표 표준값 (지표 코드 1개 = 1행)
--
-- 출처 통합: 모비젠 제안 → 협력기관 반영. 협력기관 DDL 4(지표 표준값)와 통합한 정본.
--   원본: 협력기관 수신본 4_지표_표준값.sql
--
-- 목적: 정형·비정형 지표 코드가 한 테이블(active_meta_dataset/active_meta_file)에
--       섞여도 범위 밖 적재·오생성을 FK로 차단한다.
--
-- [협력기관] active_meta_dataset / active_meta_file 이 참조한다.
--            FK는 시드 적재 뒤에 건다(코드를 표준값으로 맞춘 다음).
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS metric_registry CASCADE;

CREATE TABLE metric_registry (

    metric_code     TEXT PRIMARY KEY,
    -- 지표 코드 | 전역 유일
    -- 예) 'download_request_count', 'subscriber_count', 'content_view_count'

    label           TEXT NOT NULL,
    -- 한글명 | [협력기관] 화면 표기명
    -- 예) '다운로드·활용신청 건수', '구독자 수'

    layer           TEXT NOT NULL,
    -- 적용 레이어 | 'dataset' = active_meta_dataset, 'file' = active_meta_file
    -- 어느 이력 테이블에 적재되는 지표인지를 결정한다

    value_type      TEXT NOT NULL DEFAULT 'count',
    -- 값 유형 | count / ratio / index

    unit            TEXT,
    -- 단위 | 건 / 회 / 개 / 명

    applies_to      JSONB NOT NULL,
    -- 적용 소스 유형 | 적용 가능한 source_type 배열. ["*"] = 전체 공통
    -- 예) ["structured_file"]  ← 정형 전용
    -- 예) ["*"]                ← 정형·비정형 공통

    default_source  TEXT,
    -- 기본 수집 출처 | PORTAL_CATALOG / PORTAL_LOG / CRAWLER / API_*

    description     TEXT
    -- 설명 | 지표 정의, 산출 방식
);

CREATE INDEX idx_metric_registry_layer   ON metric_registry (layer);
CREATE INDEX idx_metric_registry_applies ON metric_registry USING GIN (applies_to);


-- ── 표준값 시드 ───────────────────────────────────────────────
-- [협력기관] 정형은 협력기관이 넣고, 비정형 코드는 모비젠이 추가한다.
-- 재실행해도 안전하도록 ON CONFLICT DO NOTHING.

-- 정형 6종 (협력기관)
INSERT INTO metric_registry (metric_code, label, layer, value_type, unit, applies_to, default_source, description)
VALUES ('download_request_count', '다운로드·활용신청 건수', 'dataset', 'count', '건', '["structured_file"]', 'PORTAL_CATALOG',
        '원천 포털 목록개방현황의 누적 건수. 증분은 직전 관측값과의 차이로 조회 시 산출'),
       ('view_count', '조회수', 'dataset', 'count', '회', '["structured_file"]', 'PORTAL_CATALOG',
        '원천 포털 누적 조회수'),
       ('file_count', '파일 수', 'dataset', 'count', '개', '["structured_file"]', 'CRAWLER',
        '데이터셋을 구성하는 파일 개수'),
       ('record_count', '데이터 건수', 'file', 'count', '건', '["structured_file"]', 'CRAWLER',
        '파일의 전체 행 수. 재수집 시 값이 변한다'),
       ('portal_download_count', '포털 다운로드 건수', 'file', 'count', '건', '["*"]', 'PORTAL_LOG',
        '포털 cetus_dataset_file.down_cnt 의 시점 관측값'),
       ('portal_search_hit_count', '포털 검색 노출 건수', 'dataset', 'count', '회', '["*"]', 'PORTAL_LOG',
        '포털 검색 로그 기반 노출 건수')
ON CONFLICT (metric_code) DO NOTHING;

-- 비정형 5종 (모비젠) — 별첨 [3. 지표 표준값] 시트의 비정형 항목
INSERT INTO metric_registry (metric_code, label, layer, value_type, unit, applies_to, default_source, description)
VALUES ('subscriber_count', '구독자 수', 'dataset', 'count', '명', '["*"]', 'CRAWLER',
        '채널 단위 구독자 수'),
       ('video_count', '영상 수', 'dataset', 'count', '개', '["*"]', 'CRAWLER',
        '채널 단위 영상 수'),
       ('content_view_count', '조회수', 'file', 'count', '회', '["*"]', 'CRAWLER',
        '개별 영상·기사 단위 조회수'),
       ('like_count', '좋아요·공감 수', 'file', 'count', '건', '["*"]', 'CRAWLER',
        '개별 콘텐츠 단위 좋아요·공감 수'),
       ('comment_count', '댓글 수', 'file', 'count', '건', '["*"]', 'CRAWLER',
        '개별 콘텐츠 단위 댓글 수')
ON CONFLICT (metric_code) DO NOTHING;

-- ⚠️ 미해결 (2026-10-28): layer='file'이고 applies_to=["*"]인 코드
--    (content_view_count·like_count·comment_count·portal_download_count)는
--    active_meta_file에 적재하게 되어 있으나, 그 테이블은 meta_datagokr_file(정형 파일)을
--    참조하므로 비정형 아이템은 FK를 만족할 수 없다.
--    현재 비정형 지표는 기존 active_meta_video / _news / _blog(wide 구조)에 적재한다.
--    협력기관 확인 필요 — 별첨에는 비정형도 active_meta_file을 쓰는 것으로 되어 있다.


-- ── 모비젠 추가 제안 (B3 그래프 분석 착수 시 등록) ────────────
-- 관계 네트워크 분석 산출물을 별도 테이블 없이 active_meta_dataset에 적재한다(ADR-012).
-- observed_at에 그래프 산출 실행 시각을 넣으면 시점별 네트워크 변화를 그대로 얻는다.
-- source 값을 'GRAPH_ANALYZER'로 두어 수집 관측값과 구분한다.
--
-- ※ 등록 시점: development/04_Implementation_Methods.md §3 B3 착수 시.
--   FK로 묶여 있어 등록 전에는 INSERT 자체가 불가능하다.
--
-- INSERT INTO metric_registry
--     (metric_code, label, layer, value_type, unit, applies_to, default_source, description) VALUES
-- ('graph_degree', '연결 차수', 'dataset', 'count', '개', '["*"]'::jsonb, 'GRAPH_ANALYZER',
--  '관계 그래프에서 해당 데이터셋에 연결된 엣지 수. 가중 차수는 weight 합'),
-- ('graph_pagerank', 'PageRank', 'dataset', 'ratio', NULL, '["*"]'::jsonb, 'GRAPH_ANALYZER',
--  '관계 그래프 내 영향력 지표. 추천 랭킹에 사용. seed 고정 필요'),
-- ('graph_community_id', '커뮤니티 ID', 'dataset', 'index', NULL, '["*"]'::jsonb, 'GRAPH_ANALYZER',
--  'Louvain 커뮤니티 탐지 결과의 군집 번호. 같은 run 안에서만 의미가 있다')
-- ON CONFLICT (metric_code) DO NOTHING;
