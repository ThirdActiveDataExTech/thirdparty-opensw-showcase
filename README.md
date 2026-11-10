# Thirdparty OpenSW Showcase

공개 데이터 원천에서 **비정형 데이터를 수집하고, 메타데이터를 표준 형식으로 정제한 뒤,
자연어로 검색할 수 있게 임베딩**하는 모듈입니다.

과학기술정보통신부 국책과제 *액티브 메타데이터 기반 데이터 관계 생성 기술 연구개발*
(RS-2024-00340834)의 공개 소프트웨어 산출물입니다.

**License:** Apache-2.0 · **Python:** 3.9+ · **DB:** PostgreSQL 17 + pgvector

> 이 저장소는 과제 공개 SW 산출물의 **스냅샷**입니다. 내부 개발 저장소와
> 실시간으로 동기화되지 않습니다.

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

다섯 단계로 따라 할 수 있습니다. 명령은 터미널(macOS: 터미널, Windows: PowerShell)에 한 줄씩 입력합니다.

**준비물**

- Python 3.9 이상, Git, [Docker Desktop](https://www.docker.com/products/docker-desktop/)(실행해 둔 상태)
- 자료를 불러올 원천의 API 키 — YouTube는 [Google Cloud 콘솔](https://console.cloud.google.com),
  네이버 뉴스·블로그는 [네이버 개발자센터](https://developers.naver.com/apps)에서 무료로 발급합니다.

| 단계 | 하는 일 | 걸리는 시간(참고) |
|---|---|---|
| 1. 데이터 내려받기 | 프로그램을 내 컴퓨터로 복사하고 필요한 부품을 설치합니다 | 1~2분 |
| 2. 데이터 저장소 켜기 | 자료를 담을 데이터베이스와 파일 저장소를 켭니다 | 1분 이내(최초에는 이미지 내려받기 몇 분) |
| 3. 자료 불러오기 | 모을 대상(채널·검색어)을 등록하고 자료를 가져옵니다 | 영상 약 340건 기준 약 9분 |
| 4. AI 검색을 위한 자료 준비(임베딩) | 문장의 뜻을 AI가 비교할 수 있는 숫자로 바꿔 둡니다 | 수 초~수 분(최초에는 모델 약 1.1GB 내려받기) |
| 5. 필요한 자료 찾기 | 궁금한 내용을 문장으로 입력해 관련 자료를 찾습니다 | 수 초 |

### 1) 데이터 내려받기

저장소를 복제하고, 이 프로젝트 전용 파이썬 환경을 만들어 필요한 라이브러리를 설치합니다.

```bash
git clone https://github.com/ThirdActiveDataExTech/thirdparty-opensw-showcase.git
cd thirdparty-opensw-showcase

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### 2) 데이터 저장소 켜기

설정 파일을 만들고 값을 채운 뒤, 데이터베이스(PostgreSQL + pgvector)와 파일 저장소(SeaweedFS, S3 호환)를 켭니다.

```bash
cp .env.example .env          # 열어서 DB_PASSWORD, S3_SECRET_KEY, API 키를 채웁니다
docker compose up -d --wait   # 두 저장소가 준비될 때까지 기다립니다
python scripts/init_schema.py # 자료를 담을 표(테이블)를 만듭니다 — 처음 한 번만
```

`init_schema.py`는 이미 표가 있으면 아무것도 바꾸지 않으므로 다시 실행해도 안전합니다.

### 3) 자료 불러오기

무엇을 모을지(수집 단위)를 등록하고, 등록할 때 알려 주는 데이터셋 ID로 수집을 실행합니다.
YouTube 채널 ID는 채널 페이지 주소의 `/channel/UC…` 부분입니다.

```bash
# 수집 단위 등록 — 예: 국가암정보센터 채널
python scripts/register_dataset.py video \
    --title "암 정보 영상" \
    --description "암 예방·검진·치료 정보를 다루는 공공 채널의 영상" \
    --subjects UCnHq2L1NAGMpb_VE_4wiSUQ \
    --keywords "암,건강정보,검진"
# → 등록 완료: urn:youtube:dataset_xxxxxx

# 수집 실행 (위에서 받은 ID를 넣습니다)
python -m src.main run urn:youtube:dataset_xxxxxx
```

뉴스·블로그는 `video` 대신 `news`·`blog`를, `--subjects`에 검색어를 쉼표로 넣습니다.
영상은 음성을 자막으로 바꾸는 작업이 함께 돌며, 1회 수집에 쓰는 시간 상한은 `.env`의
`YOUTUBE_TRANSCRIPT_BUDGET_SEC`로 정합니다.

### 4) AI 검색을 위한 자료 준비(임베딩)

모은 글과 자막을 작은 조각으로 나누고, 조각마다 뜻을 나타내는 숫자(벡터)를 만들어 저장합니다.
수집할 때 대부분 함께 만들어지며, 이 명령은 빠진 것을 채우고 결과를 보여 줍니다.

```bash
python scripts/backfill_embeddings.py
```

최초 실행 시 임베딩 모델(약 1.1GB)을 내려받습니다. 이후에는 캐시를 씁니다.

### 5) 필요한 자료 찾기

찾고 싶은 내용을 문장으로 입력합니다. 단어가 똑같지 않아도 뜻이 가까운 자료를 찾아 줍니다.

```bash
python scripts/search_demo.py "위암 조기 진단" --source video
```

`--source`는 `video`·`news`·`blog` 중에서 고릅니다.

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
