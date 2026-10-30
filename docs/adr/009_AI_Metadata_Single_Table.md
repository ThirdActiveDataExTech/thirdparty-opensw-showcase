# ADR 009: AI 생성 메타데이터 — 공통 단일 테이블 채택

> **Date:** 2026-10-27
> **Status:** Accepted

---

## 배경

AI 생성 메타데이터(요약·키워드·분류·개체명)를 저장할 구조가 필요하다.
infrastructure/03_PostgreSQL.md에는
`meta_video_ai` / `meta_news_ai` / `meta_blog_ai` 3종을
**소스별로 분리**해 두는 안이 "예정 / 설계 단계"로 기재되어 있었다.

2026-10-27 기준 **DDL은 아직 생성되지 않았다.** 지금이 구조 전환 비용이 가장 낮은 시점이다.

## 선택지

| 방식 | 장점 | 단점 |
|---|---|---|
| 소스별 `meta_*_ai` 분리 | 타입 안전, 쿼리 단순, 소스별 인덱스 최적화 | **소스 추가마다 테이블+DDL+코드 증식**, 크로스소스 검색이 UNION, 백필·재처리 로직이 소스 수만큼 복제 |
| **공통 단일 + JSONB** | 소스 추가 시 DDL 변경 0, 백필 로직 1벌, 크로스소스 검색·대시보드 용이 | 타입 안정성이 약함 |
| EAV(속성 1행) | 극단적 유연성 | 쿼리·인덱스 모두 비효율 — 비채택 |

현재 `source_type`이 이미 5종(video/news/blog/shopping_insight/persona_insight)이고,
A1(수집 어댑터화)으로 **계속 늘어나는 구조**다.

## 결정

**공통 단일 테이블 `meta_ai_annotation` + JSONB `payload`를 채택한다.**

타입 안정성 약화는 다음으로 완화한다.

- `kind` 컬럼으로 결과 종류를 구분(`summary`/`keywords`/`category`/`entities`/`image_basic`)
- `payload`에 **GIN 인덱스**
- 애플리케이션 레벨 **Pydantic 스키마 검증**
- 자주 조회하는 값만 필요 시 생성 컬럼으로 승격

### 함께 확정하는 운영 설계

1. **`generator_version = sha256(model_id | model_digest | prompt_id | prompt_hash | params)[:16]`**
   → 모델·프롬프트·파라미터 중 무엇이 바뀌어도 값이 바뀐다. 재처리 대상 추적의 단일 수단.
2. 구버전은 **UPDATE하지 않고 새 버전 행을 INSERT**(UNIQUE 키에 버전 포함) → 품질 비교·롤백 가능.
3. `input_hash`(원문 sha256)가 다르면 같은 버전이어도 재생성 대상.
4. **lease 기반 워커 큐**(`lease_owner`/`lease_until` + `FOR UPDATE SKIP LOCKED`)
   → 큐는 DB 자체. 메시지 브로커 불필요, K8s Job 재시작·OOM에 안전.
5. **필드 단위 분리 호출** — 한 번에 묶으면 한 필드 실패가 전체를 버린다.
6. 상태 3단 `success` / `partial`(성공 필드만 저장하고 계속) / `failed`,
   재시도 상한 초과 시 `skipped`로 격리.
7. **규칙 기반 품질 게이트**(길이·한국어 비율·반복률·스키마 적합) → `quality_flag`.
   위반 레코드는 저장하되 외부 노출 뷰와 패키징에서 기본 제외.

## 영향

- `infrastructure/03_PostgreSQL.md`의 `meta_*_ai` 3종 예정 항목은 **무효**가 된다. 해당 표 갱신 필요.
- 신규 테이블: `meta_ai_annotation`, `ai_generator_registry`

## 참고

- development/04_Implementation_Methods.md §3 A2
