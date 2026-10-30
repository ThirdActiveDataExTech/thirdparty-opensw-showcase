# Active Metadata Ingestion

공개 데이터 원천에서 **비정형 데이터를 수집하고, 메타데이터를 표준 형식으로 정제한 뒤,
자연어로 검색할 수 있게 임베딩**하는 모듈입니다.

과학기술정보통신부 국책과제 *액티브 메타데이터 기반 데이터 관계 생성 기술 연구개발*
(RS-2024-00340834)의 공개 소프트웨어 산출물입니다.

**License:** Apache-2.0 · **Python:** 3.9+ · **DB:** PostgreSQL 17 + pgvector

---

## 주요 공개 기능

### 1. 비정형 데이터 수집 — 5개 원천

| 원천 | 수집 단위 | 수집 항목 |
|---|---|---|
| YouTube | 채널 / 개별 영상 | 메타데이터, 통계, **자체 STT 자막** |
| 네이버 뉴스 | 검색어 | 기사 메타데이터, 본문 |
| 네이버 블로그 | 검색어 | 포스트 메타데이터, 본문, 반응 지표 |
| 네이버 쇼핑인사이트 | 카테고리 | 검색량 지수 추이 |
| 네이버 페르소나 | 카테고리 | 성별·연령대별 분포 |

수집 결과는 **DCAT 어휘**로 정제해 저장하고, 원본과 JSON-LD를 S3 호환 스토리지에
함께 보관합니다.

### 2. 자막 생성 (외부 API 불필요)

`faster-whisper`로 **로컬에서** 음성을 텍스트로 변환합니다. 외부 STT API를 쓰지
않으므로 비용과 데이터 유출 위험이 없습니다. 영상 길이의 약 1/3 시간이 듭니다
(CPU int8 6스레드 기준 실측).

### 3. 임베딩과 검색

- **문장 단위 청킹** — 문서 1건을 여러 청크로 나눠 저장합니다. 긴 문서를 통째로
  임베딩하면 짧은 질의와의 비대칭 때문에 유사도가 무너집니다
- **다국어 모델** `intfloat/multilingual-e5-base` (768차원) — 로컬 추론, API 키 불필요
- **청크 최대 유사도 집계** — 점수는 평균이 아니라 최대값을 씁니다

설계 근거는 [docs/adr/](docs/adr/)에 기록되어 있습니다.

---

## 실행 방법

### 1) 저장소 복제와 의존성 설치

```bash
git clone https://github.com/ThirdActiveDataExTech/active-metadata-ingestion.git
cd active-metadata-ingestion

python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2) 데이터베이스 기동

```bash
cp .env.example .env     # DB_PASSWORD 등 값을 채웁니다
docker compose up -d     # PostgreSQL 17 + pgvector, MinIO
```

스키마를 생성합니다.

```bash
for f in sql/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

### 3) 데이터 수집

네이버·YouTube API 키가 필요합니다. 발급처는 `.env.example`에 적어두었습니다.

```bash
# 데이터셋 등록 (수집 단위를 정의합니다)
python scripts/register_dataset.py \
    --source-type video \
    --title "반도체 기술 채널" \
    --channel-id UCWwgaK7x0_FR1goeSRazfsQ \
    --keywords "반도체,HBM,메모리"

# 수집 실행
python -m src.main --dataset-id urn:youtube:dataset_xxxxxx
```

### 4) 임베딩 생성

```bash
python scripts/backfill_embeddings.py
```

최초 실행 시 임베딩 모델(약 1.1GB)을 내려받습니다. 이후에는 캐시를 씁니다.

### 5) 검색

```bash
python scripts/search_demo.py "위암 조기 진단" --source video
```

---

## 실행 결과

```
$ python scripts/search_demo.py "위암 조기 진단" --source video

[video] "위암 조기 진단"

  1. 0.8963  위암, 대장암 검진! 20대부터 시작해야 하는 이유
            친절한 외과전문의 송쌤&김쌤
  2. 0.8848  유방암·자궁경부암·간암! 연말 전 꼭 받아야 할 검진!
            친절한 외과전문의 송쌤&김쌤
  3. 0.8825  위염, 위궤양이 위암으로? [암에 대한 바른 정보_위암]
            국가암지식정보센터
  4. 0.8805  대장내시경 후 혈변이 계속된다? | 대장내시경 합병증
            친절한 외과전문의 송쌤&김쌤
```

질의에 없던 단어("검진", "대장암", "위궤양")로도 관련 영상이 검색됩니다.
키워드 일치가 아니라 의미 유사도로 찾기 때문입니다.

```
$ python scripts/search_demo.py "HBM 고대역폭 메모리" --source video

[video] "HBM 고대역폭 메모리"

  1. 0.8926  [CHIP EASY 3편] "HBM이 뭐길래? AI 시대 가장 핫한 메모리의 정체! (2)
            SK하이닉스 [SK hynix]
  2. 0.8926  [CHIP EASY 2편] "HBM이 뭐길래? AI 시대 가장 핫한 메모리의 정체! (1)
            SK하이닉스 [SK hynix]
```

---

## 저장소 구조

```
src/
  collectors/   원천별 API 호출 (YouTube, 네이버 5종)
  pipelines/    수집 → 정제 → 저장 흐름
  database/     DCAT 테이블 적재
  embedding/    청킹 · 임베딩 · 증분 동기화
  storage/      S3 호환 스토리지, JSON-LD 내보내기
sql/            테이블 정의 (DDL)
scripts/        등록 · 백필 · 검색 데모
docs/adr/       설계 결정 기록
```

## 설계 결정 기록 (ADR)

| # | 내용 |
|---|---|
| [001](docs/adr/001_DCAT_as_metadata_standard.md) | 메타데이터 표준으로 DCAT 채택 |
| [003](docs/adr/003_VectorDB_Strategy.md) | Vector DB 전략 — pgvector 시작, Qdrant 전환 경로 |
| [009](docs/adr/009_AI_Metadata_Single_Table.md) | AI 생성 메타데이터 단일 테이블 |
| [010](docs/adr/010_Korean_Fulltext_Search.md) | 한국어 전문검색 — 앱단 토큰화 + tsvector |
| [011](docs/adr/011_Packaging_ROCrate.md) | 데이터 패키징 표준 — RO-Crate |
| [013](docs/adr/013_No_External_LLM_API.md) | 외부 LLM API 미사용 — 로컬 추론 전용 |
| [016](docs/adr/016_Embedding_Model_And_Conventions.md) | 임베딩 모델과 적재 규약 |
| [017](docs/adr/017_Unstructured_Dataset_Identifier.md) | 데이터셋 식별자 — URN 규칙 |

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE)
