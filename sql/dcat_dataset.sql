-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset : 데이터셋 전반 기술 (dcat:Dataset)
-- 모든 데이터 소스(YouTube, Naver, 뉴스 등)가 공통으로 사용
-- 1회 수집 코드 실행 = 1행 생성
--
-- 2026-10-27: 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서에 맞춰 컬럼 추가
--   source / publisher_code / theme / external_ids / party / visibility
--   category는 협력기관이 직접 반영(포털 공통 분류). theme와 별개 컬럼이다.
--   정형(source_type='structured_file')과 비정형이 이 카탈로그를 공용한다
--   기존 DB에 적용할 때는 DROP이 아니라 sql/migration_*.sql 사용
--
-- 2026-10-28: 협력기관 DDL 2(정형 데이터셋)와 통합한 정본.
--   원본: 협력기관 수신본 2_정형_데이터셋.sql
--   양측 정의가 다른 컬럼에는 [협력기관] 주석으로 상대 정의와 우리 판단을 함께 적는다.
-- ═══════════════════════════════════════════════════════════════

-- 부모 테이블이므로 CASCADE 로 자식 테이블(data_registry, dcat_dataset_vec,
-- dataset_credentials, meta_* 계열, dcat_dataset_attr, active_meta_dataset,
-- dcat_dataset_relation, meta_datagokr_file)까지 함께 삭제됨.
-- 재구성 시 자식 DDL을 이후에 순서대로 실행.
--
-- 예외: dcat_provenance는 FK를 두지 않아 삭제되지 않는다 — 데이터셋을 폐기해도
--       수집 이력은 보존한다 (협력기관 별첨 공통 규약, sql/dcat_provenance.sql 참조).
DROP TABLE IF EXISTS dcat_dataset CASCADE;

CREATE TABLE dcat_dataset (

    -- ── 식별 ──────────────────────────────────────────────────
    dataset_id          TEXT PRIMARY KEY,
    -- dct:identifier | 전체 시스템에서 유일한 데이터셋 식별자
    -- 예) 'naver_shopping_insight', 'youtube_samsung_ch', 'naver_news_ai'

    title               TEXT NOT NULL,
    -- dct:title | 데이터셋 이름
    -- 예) '네이버 쇼핑 인사이트 카테고리 수집'

    description         TEXT NOT NULL,
    -- [협력기관] nullable (정형은 결측이 잦다)
    -- ※ NOT NULL 유지 — SEMANTICALLY_RELATED 판정 근거(required_fields)라
    --   비어 있으면 관계가 아예 산출되지 않는다.
    -- dct:description | 수집 목적, 수집 방식, 특이사항 등 상세 설명
    -- title과 함께 핵심 속성으로 취급 (P02 DCAT 커버리지 목표: 핵심 속성 95%+)

    -- ── 출처 ──────────────────────────────────────────────────
    publisher           TEXT NOT NULL,
    -- [협력기관] nullable · 제공기관
    -- ※ NOT NULL 유지 — 비정형은 source와 같은 값이 항상 있다.
    -- dct:publisher | 데이터 원천 플랫폼명
    -- 예) 'Naver', 'YouTube', '연합뉴스'

    source              TEXT NOT NULL,
    -- (협력기관 별첨 신규) 출처 | 원천 포털 코드
    -- 정형) 'DATA_GO_KR', 'KOSIS', 'FIRST_PARTY'
    -- 비정형) publisher와 같은 값을 쓴다 — 'Naver', 'YouTube'
    --   (모비젠 회신 의견: "비정형 publisher 컬럼과 동일 내용 사용")
    -- publisher(제공기관)와는 별개 항목이다. 공공데이터포털 외 통계청·1st party가
    -- 합류하면서 "어느 포털에서 왔는가"를 구분할 필요가 생겨 추가됐다

    publisher_code      TEXT,
    -- (협력기관 별첨 신규) 제공기관코드 | 원천 포털의 기관 코드
    -- 비정형은 미사용 (모비젠 회신에서 추가 동의)

    source_type         TEXT NOT NULL,
    -- [협력기관] DEFAULT 'structured_file'
    -- ※ 기본값을 두지 않는다 — 비정형 등록 시 실수로 structured_file이 되면
    --   pg_meta_table 라우팅이 통째로 어긋난다.
    -- (확장) 출처 유형 분류 — data_registry.pg_meta_table 라우팅과
    -- "1 dataset = 1 source_type" 불변 규칙이 이 값의 존재를 전제로 함
    -- 값) 'video', 'news', 'blog', 'shopping_insight', 'persona_insight'

    landing_page        TEXT,
    -- dcat:landingPage | 플랫폼 공식 소개 페이지 (사람이 읽는 페이지)
    -- 예) 'https://datalab.naver.com/shopping/'

    access_url          TEXT,
    -- dcat:accessURL | API 엔드포인트 (기계가 호출하는 URL)
    -- 예) 'https://openapi.naver.com/v1/datalab/shopping/categories'

    subjects            JSONB,
    -- dct:subject | 실제 수집 대상 목록
    -- 예) ["50001421","50000204"]          ← Naver 카테고리 ID (평평한 배열)
    -- 예) ["인공지능","반도체"]             ← 뉴스/블로그 검색 키워드 (평평한 배열)
    -- 예) {"channels":["UCQrLs7LGqlcfrKDM0MXWFCQ"],"videos":["dQw4w9WgXcQ"]}
    --     ← YouTube 전용 (2026-07-28 확장): 채널 전체 발견(channels)과 관리자가
    --       직접 고른 개별 영상(videos)을 한 데이터셋에 혼합 가능. 둘 중 하나는
    --       비어있을 수 있음(예: 큐레이션 전용 데이터셋은 channels=[]).
    --       architecture/04_Collection_Pipeline_Operations.md §4.1,
    --       src/pipelines/youtube_pipeline.py 참조

    -- ── 언어 / 지역 ───────────────────────────────────────────
    language            TEXT NOT NULL DEFAULT 'ko',
    -- dct:language | ISO 639-1 언어 코드
    -- 예) 'ko', 'en'

    spatial             TEXT DEFAULT 'KR',
    -- dct:spatial | ISO 3166-1 국가 코드
    -- 예) 'KR', 'US'

    -- ── 시간 커버리지 ─────────────────────────────────────────
    temporal_start      DATE,
    -- dct:temporal 시작일 | 수집 후 자동 갱신
    -- 예) '2025-06-17'

    temporal_end        DATE,
    -- dct:temporal 종료일 | NULL = 현재 진행 중(open-ended)
    -- 예) '2026-06-16', NULL

    temporal_resolution TEXT,
    -- dcat:temporalResolution | 데이터 1건의 시간 단위 (ISO 8601)
    -- 예) 'P1D'(일간), 'P7D'(주간), NULL(시점 없음 - 영상 메타 등)

    accrual_periodicity TEXT,
    -- dct:accrualPeriodicity | 수집(갱신) 주기 (ISO 8601)
    -- 예) 'P1D'(매일), 'P7D'(매주), 'irregular'(비정기)

    -- ── 데이터 규모 ───────────────────────────────────────────
    item_count          BIGINT,
    -- [협력기관] 구성 데이터파일 수 · INTEGER
    -- ※ BIGINT 유지 — data_registry.item_count(BIGINT)의 미러이므로 타입을 맞춘다.
    --   넘침 위험 때문은 아니다(실측 최대 17,932, INTEGER 상한 21억).
    -- (확장) DCAT/DCT에 대응 표준 용어 없음 — source_type과 같은 자체 확장 필드
    -- 이 데이터셋을 구성하는 고유 아이템 수 | temporal_start/end와 동일하게
    -- 수집 후 자동 갱신되며 data_registry.item_count와 동기화된다
    -- 예) YouTube 영상 수, 뉴스 기사 수, 블로그 게시물 수, 쇼핑/Persona 카테고리 수
    -- (data_registry.item_count가 운영 중 실시간으로 갱신되는 원본이고,
    --  여기 값은 dcat_dataset 조회만으로 데이터셋 규모를 바로 알 수 있도록 둔 미러)

    -- ── 태그 ──────────────────────────────────────────────────
    keywords            JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- dcat:keyword | 검색·분류용 키워드 (JSON 배열)
    -- 예) ["쇼핑","검색량","카테고리","네이버"]
    -- 협력기관 KEYWORD_OVERLAP 관계 판정의 근거 컬럼이다
    -- (relation_type_registry.required_fields = ["keywords"])

    theme               JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- dct:subject | 분류체계 | '대분류 - 소분류' 문자열을 배열로 분해해 보관
    -- 협력기관 별첨 테이블정의서 기준 신규 컬럼. 정형·비정형 공용.
    -- 예) ["보건의료","의료서비스"]
    -- 비정형은 사용자가 등록 시 분류를 설정하는 방향 (모비젠 회신 의견)
    --
    -- 협력기관 회신: 비정형은 사용자가 등록 시 분류를 설정하는 방향으로 채운다.
    -- 아래 category(포털 공통 분류)와는 다른 컬럼이다 — 둘 다 사용한다.

    category            JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 공통 분류 | 국가지식정보 통합플랫폼 「디지털 집현전」 주제 분류 준용
    -- 대분류 7 / 중분류 76. 값 표기는 '대분류 > 중분류' (구분 기호 ' > ' 앞뒤 공백 1칸)
    -- 예) ["의료 > 질병관리", "의료 > 공중보건"]
    -- 데이터셋당 1~3개, 첫 번째 값이 대표 분류. 분류표 밖의 값·중복 불가
    --
    -- theme와는 별개 컬럼이다 — 둘 다 사용한다
    --   theme    = 원천 포털이 부여한 분류 '원문' (포털마다 체계가 다름, 원천 정보 보존)
    --   category = 모든 데이터에 동일한 공통 분류 (포털 전체 분류·필터링)
    --
    -- 협력기관이 컬럼과 GIN 인덱스를 모비젠 서버에 반영 완료.
    -- 분류표 전문·부여 규칙·비정형 부여 방법은 database/category_taxonomy.md 참조
    -- ⚠️ CHECK 제약이 없으므로 DB가 오타를 막아주지 않는다. 앱에서 분류표 대조 필수

    -- ── 이용 조건 ─────────────────────────────────────────────
    license             TEXT,
    -- dct:license | 데이터 이용 라이선스 식별자 또는 URI
    -- 예) "https://developers.naver.com/notice/terms"          ← Naver API 이용약관
    -- 예) "https://developers.google.com/youtube/terms/api-services-tos" ← YouTube API ToS
    -- 예) "https://www.kogl.or.kr/info/license.do#01-tab"     ← 공공누리 제1유형
    -- 예) "https://creativecommons.org/licenses/by/4.0/"      ← CC BY 4.0

    rights              TEXT,
    -- dct:rights | 라이선스 URI로 표현하기 어려운 세부 이용 조건 (자유 텍스트)
    -- 예) "네이버 API 이용약관 준수. 외부 배포 및 상업적 재판매 금지."
    -- 예) "YouTube API ToS 준수. 제3자 제공 시 Google 사전 승인 필요."
    -- 예) "출처 표시 조건 하에 자유로운 이용 가능. 상업적 이용 및 변경 허용."

    -- ── 생성 주체 ─────────────────────────────────────────────
    dataset_origin      TEXT NOT NULL DEFAULT 'admin',
    -- 데이터셋 생성 주체
    -- 'admin' : 관리자가 생성 (채널 1개, 검색어 1개 등 단일 대상 자동 수집)
    -- 'user'  : 사용자가 UI에서 직접 생성 (동일 소스 타입 내 복수 채널·영상·검색어 자유 조합)
    --           예) YouTube 데이터셋: 채널 여러 개 + 개별 영상 선택
    --           주의: source_type이 다른 항목(YouTube+뉴스 혼합 등)은 지원하지 않음

    owner_id             TEXT,
    -- 데이터셋을 생성한 사용자 식별자. 플랫폼 계정 테이블(같은 datagokr DB 안에
    -- 별도 스키마로 생성 예정, 다른 팀 작업 — 2026-07-23 기준 테이블 스펙 미정)의
    -- PK를 참조할 예정이나, 아직 그 테이블이 없어 지금은 FK 제약 없이 값만 저장한다.
    -- 계정 테이블 생성 후 실제 PK 컬럼명/타입 확인하여 ALTER TABLE로 FK 추가 필요
    -- (architecture/04_Collection_Pipeline_Operations.md §10, NEXT_STEPS.md 2-6 참조)
    -- dataset_origin='admin'이면 특정 사용자 소유가 아니므로 NULL 허용

    -- ── 연계 · 권한 (협력기관 별첨 신규) ─────────────────────
    external_ids        JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- adms:identifier | 외부 식별자 | 원천 포털이 데이터셋에 붙여 둔 고유번호
    -- 형식: '포털:번호' 문자열의 배열 (협력기관 회신, 2026-10-27)
    -- 예) ["datagokr:15135932"]
    -- 예) ["kosis:DT_1B34E17", "kosis-stat:1999038"]  ← 뒤는 그 통계표가 속한 통계 번호
    -- 용도: 같은 데이터셋이 다른 경로로 두 번 수집되면 이 번호가 같게 나온다.
    --       중복 데이터셋을 찾아 하나로 합칠 때 쓴다
    --
    -- 비정형(2026-10-28 현행). 형식은 동일하게 유지한다 — 객체가 아니라
    -- '네임스페이스:값' 문자열 배열. 세 종류가 들어가고 값 자체로 구분된다.
    --
    --   youtube:UCWwgaK7x0_FR1goeSRazfsQ      원천(YouTube) 발급 채널 ID
    --   naver:news:sha256-3c639c929baf        수집 조건 집합 해시 (합성값)
    --   legacy:naver_news_ai                  URN 전환 전 우리 식별자
    --
    -- ⚠️ 해시에 'sha256-' 접두를 붙이는 이유: 이 컬럼의 본뜻(adms:identifier)은
    --    "어떤 기관이 발급한 식별자"인데 해시는 합성값이라 원천에 조회되지 않는다.
    --    접두가 없으면 naver:news:3c639c929baf 가 네이버 발급 ID처럼 보인다.
    --    동등성 비교라는 기능은 같다.
    --
    -- 뉴스·블로그의 검색어와 쇼핑·페르소나의 카테고리를 개별 값으로 넣지 않고
    -- 집합 해시로 넣는 이유: 조건 하나만 겹쳐도 오탐이 난다. 실제로
    -- shopping_insight와 shopping_insight_advertiser는 카테고리 50000148을 공유한다.
    -- 집합 전체를 해시하면 완전히 같을 때만 겹친다.
    -- 규칙 상세: docs/database/dataset_id_urn_migration.md §7

    party               TEXT,
    -- 파티 구분 | '1st' / '3rd'
    -- 포털 cetus_dataset_file.data_tp_cd와 대응 (정형·비정형 동일 방식)

    visibility          TEXT NOT NULL DEFAULT 'ORG',
    -- 공개 범위 | PUBLIC / ORG / PRIVATE · 포털 권한 판정의 원본
    -- 기본값을 ORG로 둔다 — PUBLIC을 기본으로 하면 등록 실수가 곧 외부 공개가 된다.
    -- 공개가 필요한 데이터셋은 등록 시 명시적으로 PUBLIC을 지정한다

    -- ── 관리 ──────────────────────────────────────────────────
    version             TEXT NOT NULL DEFAULT '1.0',
    -- owl:versionInfo | 수집 방식 변경 시 버전 올림

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- dct:issued | 데이터셋 최초 등록 일시

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    -- dct:modified | 마지막 수집 또는 메타데이터 수정 일시
);

-- 검색용 인덱스
-- ── 인덱스 ────────────────────────────────────────────────────
-- 모비젠(운영·비정형) + 협력기관(검색 필터·관계 판정) 양측을 합친 것

-- 모비젠 — 운영 조회
CREATE INDEX idx_dcat_dataset_source_type  ON dcat_dataset (source_type);
CREATE INDEX idx_dcat_dataset_updated      ON dcat_dataset (updated_at DESC);
CREATE INDEX idx_dcat_dataset_owner        ON dcat_dataset (owner_id);
CREATE INDEX idx_dcat_dataset_source       ON dcat_dataset (source);
CREATE INDEX idx_dcat_dataset_visibility   ON dcat_dataset (visibility);

-- 협력기관 — 검색 필터·관계 판정
CREATE INDEX idx_dcat_dataset_publisher    ON dcat_dataset (publisher);
CREATE INDEX idx_dcat_dataset_party        ON dcat_dataset (party);
CREATE INDEX idx_dcat_dataset_periodicity  ON dcat_dataset (accrual_periodicity);
CREATE INDEX idx_dcat_dataset_temporal     ON dcat_dataset (temporal_start, temporal_end);

-- JSONB 포함 검색 (GIN) — KEYWORD_OVERLAP 판정과 분류 필터의 전제
CREATE INDEX idx_dcat_dataset_keywords     ON dcat_dataset USING GIN (keywords);
CREATE INDEX idx_dcat_dataset_theme        ON dcat_dataset USING GIN (theme);
CREATE INDEX idx_dcat_dataset_category     ON dcat_dataset USING GIN (category);
CREATE INDEX idx_dcat_dataset_external_ids ON dcat_dataset USING GIN (external_ids);
