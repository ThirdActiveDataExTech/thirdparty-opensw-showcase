-- ═══════════════════════════════════════════════════════════════
-- dcat_dataset_vec : 데이터셋 카탈로그 단위 임베딩 (pgvector)
--
-- dcat_dataset 1건 = **청크 N건** (PK: dataset_id + chunk_index)
--
-- ⚠️ 2026-10-29 구조 변경: 1:1 → 1:N (청킹)
--    아이템 벡터 테이블(meta_*_vec)과 같은 이유다. 모델이 짧은 질의 ↔ 긴 문서
--    비대칭 비교에서 무너져, 문장/줄 단위로 쪼개 청크별로 임베딩한다.
--    검색은 **청크 최대 유사도**로 집계한다.
--    docs/database/embedding_chunking.md 참조
--
--    데이터셋 텍스트(제목+설명+키워드)는 아이템보다 짧아 청크가 1~3개에
--    그치는 경우가 많지만, 구조를 아이템 쪽과 맞춰 검색 쿼리를 한 벌로 쓴다.
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS dcat_dataset_vec CASCADE;

CREATE TABLE dcat_dataset_vec (

    dataset_id   TEXT NOT NULL
                 REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,
    -- ON UPDATE CASCADE: dataset_id는 URN이고 전환 이력이 있다(2026-10-28)
    -- ON DELETE CASCADE: 데이터셋 삭제 시 청크도 전부 삭제

    chunk_index  INTEGER NOT NULL,
    -- 0부터. 원문에서의 순서

    embedding    vector(768) NOT NULL,
    -- multilingual-e5-base 기준 768차원 (2026-10-29 전환, 차원 동일)
    -- 모델을 바꾸면 차원이 달라지므로 이 테이블을 재생성해야 한다

    embed_text   TEXT NOT NULL,
    -- 이 청크의 원본 텍스트 (재현·디버깅용, 증분 판정의 기준)
    -- 원문 형식: "{title}. {description}. 키워드: {keywords}"

    model_name   TEXT NOT NULL
                 DEFAULT 'intfloat/multilingual-e5-base',

    embedded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (dataset_id, chunk_index)
);

CREATE INDEX idx_dcat_dataset_vec_dataset ON dcat_dataset_vec (dataset_id);

-- 코사인 유사도 검색용 인덱스
-- ⚠️ 빌드 전 maintenance_work_mem을 올릴 것. 서버 기본 64MB에서는 약 17,700행부터
--    그래프가 메모리를 넘겨 느린 디스크 경로로 전환된다(실측: 276행/초 → 77행/초).
--    1GB로 올리면 484행/초. docs/database/vec_schema_unification_proposal.md §7.4
-- CREATE INDEX ON dcat_dataset_vec USING hnsw (embedding vector_cosine_ops);
