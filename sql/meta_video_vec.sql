-- ═══════════════════════════════════════════════════════════════
-- meta_video_vec : YouTube 영상 단위 임베딩 (pgvector)
--
-- meta_video 1건 = **청크 N건** (PK: meta_id + chunk_index)
--
-- ⚠️ 2026-10-29 구조 변경: 1:1 → 1:N (청킹)
--    이전에는 "meta_video 1건 = 벡터 1개"였는데 **검색이 동작하지 않았다.**
--    모델(paraphrase-multilingual-mpnet-base-v2)은 문장쌍 패러프레이즈용이라
--    짧은 질의 ↔ 긴 문서의 비대칭 비교에서 유사도가 무너진다. 실측:
--
--      질의 "위암 수술 후 관리"
--        문서 앞 10자(= 질의와 동일)          cos 1.0000
--        문서 앞 40자(+ "김희성 교수 / …")     cos 0.0292   ← 무너짐
--        무관한 문장("고양이 사진")            cos 0.0832
--
--    제목이 글자까지 같은 영상이 29,029건 중 17,449위였다.
--    문장/줄 단위로 쪼개 청크별로 임베딩하고, 검색은 **청크 최대 유사도**로
--    집계하면 정답이 1위로 올라온다(실측 1.0000).
--
--    docs/database/embedding_chunking.md 참조
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS meta_video_vec CASCADE;

CREATE TABLE meta_video_vec (

    meta_id     BIGINT NOT NULL
                REFERENCES meta_video(id) ON DELETE CASCADE,
    -- ON DELETE CASCADE: 원본 삭제 시 청크도 전부 삭제

    chunk_index INTEGER NOT NULL,
    -- 0부터. 원문에서의 순서. 재생성 시 같은 입력이면 같은 번호가 나와야 한다

    embedding   vector(768) NOT NULL,
    -- multilingual-e5-base 기준 768차원 (2026-10-29 전환, 차원 동일)
    -- 모델을 바꾸면 차원이 달라지므로 이 테이블을 재생성해야 한다

    embed_text  TEXT NOT NULL,
    -- 이 청크의 원본 텍스트 (재현·디버깅용, 증분 판정의 기준)
    -- 원문 형식: "{title}. {description}. 태그: {tags}"

    model_name  TEXT NOT NULL
                DEFAULT 'intfloat/multilingual-e5-base',

    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (meta_id, chunk_index)
);

-- 특정 원본의 청크를 한 번에 지우고 다시 넣을 때 쓴다
CREATE INDEX idx_meta_video_vec_meta ON meta_video_vec (meta_id);

-- 코사인 유사도 검색용 인덱스
-- 청킹으로 행 수가 원본의 수 배가 되므로 데이터가 쌓이면 필요하다.
-- ⚠️ 빌드 전 maintenance_work_mem을 올릴 것. 서버 기본 64MB에서는 약 17,700행부터
--    그래프가 메모리를 넘겨 느린 디스크 경로로 전환된다(실측: 276행/초 → 77행/초).
--    1GB로 올리면 484행/초. 자세한 측정은 docs/database/vec_schema_unification_proposal.md §7.4
-- CREATE INDEX ON meta_video_vec USING hnsw (embedding vector_cosine_ops);
