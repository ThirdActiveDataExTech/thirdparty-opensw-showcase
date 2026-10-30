# ADR 003: Vector DB 전략 — pgvector 시작, Qdrant 전환 경로 확보

> **Date:** 2026-07-01
> **Status:** Accepted

---

## 배경

`dcat_dataset.description`을 벡터화하여 사용자가 자연어 질의로 데이터셋을 탐색할 수 있는 기능이 필요하다.

현재 벡터화 대상: 데이터셋 description, title, keywords (30+ 데이터셋 → 수백 개 벡터)
향후 확장 가능성: 뉴스 기사 본문, YouTube 영상 description → 수십만 개 이상

---

## 결정

**현재: pgvector** (PostgreSQL 확장)
**향후: Qdrant** (벡터 수가 많아지거나 고도화 필요 시 전환)

---

## 현재 — pgvector 채택 이유

- 이미 PostgreSQL(datagokr)을 사용 중 → 별도 서비스 불필요
- 데이터셋 description 수준(수백 개 벡터)에서 성능 충분
- `dcat_dataset`과 JOIN 쿼리가 SQL 한 줄로 가능
- K8s에 새 Deployment 추가 불필요

### 구현 방식

```sql
-- PostgreSQL pgvector 확장 설치
CREATE EXTENSION IF NOT EXISTS vector;

-- dcat_dataset에 벡터 컬럼 추가 (별도 테이블로 분리도 가능)
CREATE TABLE dcat_dataset_vec (
    dataset_id   TEXT PRIMARY KEY REFERENCES dcat_dataset(dataset_id),
    embedding    vector(768),         -- 오픈소스 모델 기준 (768차원)
    embedded_at  TIMESTAMPTZ DEFAULT now()
);

-- 유사도 검색 예시
SELECT d.dataset_id, d.title, d.description,
       1 - (v.embedding <=> query_vec) AS similarity
FROM dcat_dataset_vec v
JOIN dcat_dataset d ON d.dataset_id = v.dataset_id
ORDER BY v.embedding <=> query_vec
LIMIT 5;
```

### 임베딩 모델

**원칙: API 비용 없는 오픈소스 모델만 사용한다.**

| 모델 | 차원 | 한국어 | 추천 이유 |
|------|------|--------|----------|
| `BAAI/bge-m3` | 1024 | 우수 | 다국어 최고 성능, HuggingFace 무료 |
| `paraphrase-multilingual-mpnet-base-v2` | 768 | 양호 | 가볍고 안정적, 가장 널리 쓰임 |
| `jhgan/ko-sroberta-multitask` | 768 | 최적 | 한국어 특화, 한국어 문장 유사도 최적화 |

**채택: `paraphrase-multilingual-mpnet-base-v2` (768차원)**

이유:
- API 비용 없음 (HuggingFace 자체 호스팅 또는 `sentence-transformers` 라이브러리로 로컬 실행)
- 768차원으로 pgvector 인덱스 크기 적절
- description, title, keywords가 혼합된 다국어 텍스트에 안정적
- 향후 `jhgan/ko-sroberta-multitask`로 교체 시 차원 동일 (768) → DDL 변경 불필요

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
vec = model.encode("네이버 쇼핑 인사이트 카테고리별 검색량 지수")
# → shape: (768,)
```

---

## 전환 조건 — Qdrant로 이전하는 시점

다음 중 하나를 충족하면 Qdrant 전환을 검토한다.

- 벡터 수 10만 개 이상 (뉴스 기사, YouTube 영상 본문 등 개별 콘텐츠 벡터화 시)
- 복잡한 메타데이터 필터링이 필요한 경우 (Qdrant payload filter)
- pgvector 쿼리 응답 시간 1초 이상 지속 시

---

## 전환 방법 — pgvector → Qdrant

코드 변경 범위가 제한적이라 안전하게 전환 가능하다.

```
1. Qdrant K8s Deployment 배포 (병렬 운영)
2. 기존 vectors를 PostgreSQL에서 꺼내 Qdrant에 삽입
   (임베딩 재계산 없이 vector 값 그대로 이전)
3. 쿼리 레이어(storage/vector_search.py)만 교체
4. 검증 후 pgvector 컬럼 제거
```

임베딩 모델은 변경하지 않으므로 수집 코드와 전처리 파이프라인은 무관하다.
