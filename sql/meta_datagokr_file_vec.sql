-- ═══════════════════════════════════════════════════════════════
-- meta_datagokr_file_vec : 데이터파일 임베딩 (파일 1건 = 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 모비젠 *_vec 패턴(1:1 분리)을 그대로 따른다 — 재임베딩이 본 테이블에 잠금을 걸지 않는다.
--
-- 비정형 *_vec과의 차이: 벡터가 2개다(요약 / 키워드). 비정형은 embedding 1개.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS meta_datagokr_file_vec CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE meta_datagokr_file_vec (

    file_id             TEXT PRIMARY KEY
                        REFERENCES meta_datagokr_file(file_id) ON DELETE CASCADE,
    -- 데이터파일 식별자

    summary_embedding   vector(768),
    -- 요약 임베딩 | meta_datagokr_file.table_summary 기반

    keywords_embedding  vector(768),
    -- 키워드 임베딩 | [협력기관] 키워드 평균 (별첨은 '컬럼명·키워드 평균')

    embed_text          TEXT,
    -- 임베딩 원문 | 재현성 확보

    model_name          TEXT NOT NULL,
    -- 모델명 | 모델 교체 시 재임베딩 대상 판별
    -- 주의: 정형·비정형 임베딩 모델 통일 여부는 협력기관과 협의 미결 (별첨 명시)

    embedded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 요약 임베딩 기반 유사 검색용 (정형은 파일 수가 많아 인덱스를 생성해 둔다)
CREATE INDEX idx_meta_datagokr_file_vec_summary
    ON meta_datagokr_file_vec USING hnsw (summary_embedding vector_cosine_ops);
