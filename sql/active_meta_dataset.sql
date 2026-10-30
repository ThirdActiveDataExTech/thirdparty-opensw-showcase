-- ═══════════════════════════════════════════════════════════════
-- active_meta_dataset : 데이터셋 이력 메타데이터 (관측 1건 = 1행)
--
-- 협력기관 「백엔드 설계 초안」 v2 별첨 테이블정의서 기준. [신규]
-- 데이터셋 단위 지표의 "그 시점 관측값"만 저장한다. 변화량은 저장하지 않는다.
--
-- 기존 비정형 active_meta_*(youtube/news/blog/shopping/persona)와의 관계:
--   - 기존 비정형은 타입 컬럼(wide) + delta 저장 방식을 유지한다 (NEXT_STEPS.md §7.4)
--   - 이 테이블은 EAV(metric_code) 방식이며 신규 정형에 우선 적용한다
--   - 비정형 중 데이터셋 단위 지표(구독자 수·영상 수)는 이 테이블도 사용할 수 있다
--     (metric_registry.applies_to = ["*"] 인 코드)
--
-- 적재 규칙 (별첨 [3. 지표 표준값] 시트):
--   - 수집 주기: 일 1회 기준
--   - 무변화 시 적재하지 않는다 (직전 관측값과 같으면 skip).
--     변화량은 실제 변화가 발생한 관측 간격 기준으로 계산되므로 정확도 손실이 없다
--   - 변화량은 저장하지 않고 조회 시 계산한다 (모비젠 v_*_latest와 같은 계약의 뷰)
-- 출처 통합: 협력기관 DDL과 통합한 정본. 원본은 협력기관 수신본  참조.
-- ═══════════════════════════════════════════════════════════════
DROP TABLE IF EXISTS active_meta_dataset CASCADE;

CREATE TABLE active_meta_dataset (

    id              BIGSERIAL PRIMARY KEY,
    -- 관측 ID

    dataset_id      TEXT NOT NULL
                    REFERENCES dcat_dataset(dataset_id)
                    ON UPDATE CASCADE ON DELETE CASCADE,
    -- 데이터셋 식별자 | dcat_dataset 참조

    metric_code     TEXT NOT NULL
                    REFERENCES metric_registry(metric_code) ON UPDATE CASCADE,
    -- 지표 코드 | metric_registry 참조 (layer='dataset'인 코드만 적재)
    -- [협력기관] 지표 표준값 · FK는 레지스트리 시드 적재 뒤에 건다
    --            (기존 코드를 표준값으로 맞춘 다음이어야 FK가 걸린다)

    metric_value    NUMERIC(20,4) NOT NULL,
    -- 관측값 | 변화량이 아니라 "그 시점의 값"

    observed_at     TIMESTAMPTZ NOT NULL,
    -- 관측 시각

    source          TEXT NOT NULL,
    -- 수집 출처 | PORTAL_CATALOG / PORTAL_LOG / CRAWLER

    UNIQUE (dataset_id, metric_code, observed_at)
    -- 같은 데이터셋·지표·시각의 중복 관측 차단
);

-- 적재량 상한 참고: 데이터셋 10만 건 × 지표 5종 × 일 1회 = 연 1.8억 건.
-- 복합 UNIQUE 인덱스로 충분하며, 초과 시 observed_at 기준 파티셔닝으로 무중단 전환한다.
