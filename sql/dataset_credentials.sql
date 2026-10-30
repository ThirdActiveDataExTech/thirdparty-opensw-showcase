-- ═══════════════════════════════════════════════════════════════
-- dataset_credentials : 데이터셋별 API Key 등 자격증명 (암호화 저장)
--
-- 배경: 플랫폼 프론트엔드에서 데이터셋 등록 시 사용자가 자신의 API Key를
-- 직접 입력하는 것을 기본으로 한다 (architecture/04_Collection_Pipeline_Operations.md §6).
-- dcat_dataset과 분리된 별도 테이블에 두는 이유:
--   1) 민감정보를 일반 조회/조인이 잦은 dcat_dataset과 물리적으로 분리해
--      실수로 API 응답에 섞여 나가는 사고를 구조적으로 방지
--   2) 이 테이블에 대한 DB 권한을 Collector 실행 계정으로만 좁힐 수 있음
--
-- 암호화 방식: pgcrypto의 pgp_sym_encrypt/pgp_sym_decrypt (대칭키).
-- 대칭키 자체는 DB에 저장하지 않고 K8s Secret(dataset-credentials-encryption-key)에
-- 별도 보관 — DB 접근 권한만으로는 평문 복호화가 불가능하도록 분리.
--
-- Fallback 규칙: 이 테이블에 해당 dataset_id 행이 없으면 Collector는
-- 플랫폼 공유 키(예: youtube-api-secret)로 폴백한다. 즉 사용자가 직접 키를
-- 입력하지 않아도 데이터셋 등록 자체는 가능하다 (운영 정책으로 강제할지는 별도 결정).
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS dataset_credentials;

CREATE TABLE dataset_credentials (

    -- ── 식별 ──────────────────────────────────────────────────
    dataset_id          TEXT NOT NULL
                        REFERENCES dcat_dataset(dataset_id) ON UPDATE CASCADE ON DELETE CASCADE,

    credential_type     TEXT NOT NULL,
    -- 자격증명 종류 — Collector가 어떤 키인지 구분하는 용도
    -- 예) 'youtube_api_key', 'naver_client_id', 'naver_client_secret'

    UNIQUE (dataset_id, credential_type),
    -- 데이터셋 하나가 여러 종류의 키를 가질 수 있음 (예: Naver는 client_id + client_secret 2건)

    -- ── 암호화된 값 ───────────────────────────────────────────
    encrypted_value      BYTEA NOT NULL,
    -- pgp_sym_encrypt(평문, 암호화 키)의 결과
    -- 암호화 키는 이 DB가 아니라 K8s Secret에 별도 보관 (헤더 주석 참조)

    -- ── 관리 ──────────────────────────────────────────────────
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 사용자가 키를 재발급/교체한 경우 갱신

    last_used_at          TIMESTAMPTZ
    -- Collector가 이 키로 마지막 성공 호출한 시각 (만료/폐기된 키 추적용)
);

CREATE INDEX idx_dataset_credentials_dataset ON dataset_credentials(dataset_id);

-- ═══════════════════════════════════════════════════════════════
-- 사용 예시 (애플리케이션 코드에서는 파라미터 바인딩으로 암호화 키를 주입한다.
-- 아래는 형태 설명용 — 실제 암호화 키를 SQL에 리터럴로 쓰지 않는다)
-- ═══════════════════════════════════════════════════════════════
--
-- 저장 (데이터셋 등록 API):
--   INSERT INTO dataset_credentials (dataset_id, credential_type, encrypted_value)
--   VALUES (%(dataset_id)s, 'youtube_api_key', pgp_sym_encrypt(%(api_key)s, %(enc_key)s));
--
-- 조회 (Collector 실행 시, 없으면 플랫폼 공유 키로 폴백):
--   SELECT pgp_sym_decrypt(encrypted_value, %(enc_key)s)
--   FROM dataset_credentials
--   WHERE dataset_id = %(dataset_id)s AND credential_type = 'youtube_api_key';
