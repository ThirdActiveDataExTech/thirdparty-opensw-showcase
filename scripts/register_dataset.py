"""신규 데이터셋 등록 헬퍼 (관리자/개발용 CLI).

runbooks/04_Add_New_Dataset_Existing_Source.md의 "A. 신규 데이터셋 생성" 절차를
그대로 구현한다. §6.3(프론트엔드 등록 API)와 Airflow가 아직 없어서, 지금은 이
스크립트로 dcat_dataset/data_registry(+선언형이면 meta_shopping_insight/persona)를
채우고 `python -m src.main run <dataset_id>`로 수동 트리거하는 게 실질적인
등록~수집 경로다.

사용 예:
  # 발견형 (YouTube) — 다른 채널을 새 데이터셋으로
  python scripts/register_dataset.py video \\
      --title "SK하이닉스 공식 채널" --description "SK하이닉스 유튜브 채널 영상 수집" \\
      --subjects UCltyil2FaQZZ4kUNinKkKmw --origin admin

  # 발견형 (YouTube) — 채널 전체 + 개별 영상 큐레이션을 한 데이터셋에 혼합
  python scripts/register_dataset.py video \\
      --title "위암수술전 환자 추천영상" --description "..." \\
      --subjects UCltyil2FaQZZ4kUNinKkKmw \\
      --videos dQw4w9WgXcQ,abc123XYZde --origin admin

  # 선언형 (쇼핑인사이트) — 다른 카테고리 조합을 새 데이터셋으로, 소급 수집 시작일 지정
  python scripts/register_dataset.py shopping_insight \\
      --title "IT/가전 카테고리 쇼핑 인사이트" --description "..." \\
      --categories "50000003:디지털/가전,50000005:가구/인테리어" --origin admin \\
      --temporal-start 2025-01-01

등록 후 실제 수집을 트리거하려면:
  python -m src.main run <출력된-dataset_id>
"""

import argparse
import hashlib
import json
import re
import secrets

from src.database.db import get_conn

DISCOVERY_TYPES = {"video", "news", "blog"}
DECLARATIVE_TYPES = {"shopping_insight", "persona_insight"}

# 비정형은 전부 외부 원천에서 가져온다 — 1st(자체 생산)가 아니라 3rd다.
# 정형(공공데이터포털)은 협력기관이 포털 메타데이터를 보고 직접 채운다.
PARTY_THIRD_PARTY = "3rd"

_SOURCE_META = {
    "video": {
        "urn_namespace": "youtube",
        "publisher": "YouTube",
        "pg_meta_table": "meta_video",
        "pg_active_table": "active_meta_video",
        "license": "https://developers.google.com/youtube/terms/api-services-tos",
        "landing_page": "https://www.youtube.com/",
        "access_url": "https://www.googleapis.com/youtube/v3/",
        "rights": "YouTube API Services Terms of Service 준수. 수집 데이터의 제3자 제공 시 Google 사전 승인 필요.",
        "temporal_resolution": None,
    },
    "news": {
        "urn_namespace": "naver",
        "publisher": "Naver",
        "pg_meta_table": "meta_news",
        "pg_active_table": "active_meta_news",
        "license": "https://developers.naver.com/notice/terms",
        "landing_page": "https://search.naver.com/search.naver?where=news",
        "access_url": "https://openapi.naver.com/v1/search/news.json",
        "rights": "네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.",
        "temporal_resolution": None,
    },
    "blog": {
        "urn_namespace": "naver",
        "publisher": "Naver",
        "pg_meta_table": "meta_blog",
        "pg_active_table": "active_meta_blog",
        "license": "https://developers.naver.com/notice/terms",
        "landing_page": "https://search.naver.com/search.naver?where=blog",
        "access_url": "https://openapi.naver.com/v1/search/blog.json",
        "rights": "네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.",
        "temporal_resolution": None,
    },
    "shopping_insight": {
        "urn_namespace": "naver",
        "publisher": "Naver",
        "pg_meta_table": "meta_shopping_insight",
        "pg_active_table": "active_meta_shopping_insight",
        "license": "https://developers.naver.com/notice/terms",
        "landing_page": "https://datalab.naver.com/shopping/",
        "access_url": "https://openapi.naver.com/v1/datalab/shopping/categories",
        "rights": "네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.",
        "temporal_resolution": "P1D",
    },
    "persona_insight": {
        "urn_namespace": "naver",
        "publisher": "Naver",
        "pg_meta_table": "meta_persona_insight",
        "pg_active_table": "active_meta_persona_insight",
        "license": "https://developers.naver.com/notice/terms",
        "landing_page": "https://datalab.naver.com/shopping/",
        "access_url": "https://openapi.naver.com/v1/datalab/shopping/category/gender,age",
        "rights": "네이버 API 이용약관 준수. 수집 데이터의 외부 배포 및 상업적 재판매 금지.",
        "temporal_resolution": "P1D",
    },
}


# 협력기관 별첨 테이블정의서가 규정한 dataset_id 형식 (TEXT 최대 100자).
# 2026-10-28 전환 완료 — docs/database/dataset_id_urn_migration.md
URN_RE = re.compile(r"^urn:[a-z0-9]+:[a-z0-9_]+$")


def _urn_key_prefix(source_type: str) -> str:
    """네임스페이스가 source_type을 결정하지 못할 때만 키 앞에 붙일 접두를 돌려준다.

    `youtube` 네임스페이스에는 source_type이 `video` 하나뿐이라 네임스페이스만으로
    종류가 정해진다 → 접두 없음 (`urn:youtube:samsung_official`).
    `naver`에는 news·blog·shopping_insight·persona_insight 넷이 들어오므로
    키에 넣지 않으면 구분이 안 된다 → 접두 있음 (`urn:naver:news_ai`).

    _SOURCE_META에서 세어 판단하므로, 나중에 한 네임스페이스에 source_type이
    늘면 그때부터 자동으로 접두가 붙는다. 그 시점 이전에 만들어진 식별자는
    그대로 두면 된다 — 접두 유무가 유일성에 영향을 주지는 않는다.
    """
    ns = _SOURCE_META[source_type]["urn_namespace"]
    siblings = sum(1 for m in _SOURCE_META.values() if m["urn_namespace"] == ns)
    return "" if siblings == 1 else f"{source_type}_"


def make_dataset_id(conn, source_type: str) -> str:
    """urn:{네임스페이스}:{source_type}_dataset_{랜덤접미}. 충돌 시 재시도 (§7.1).

        뉴스      → urn:naver:news_dataset_a3f1c2
        블로그     → urn:naver:blog_dataset_7d2e91
        유튜브     → urn:youtube:dataset_5c81af      (youtube는 video 하나뿐)

    **제목에서 키를 만들지 않는다.** 이전에는 slugify(title)을 썼는데,
    영문·숫자만 남기는 방식이라 결과를 예측할 수 없었다.

        'AI 관련 뉴스'  → 'ai'       (AI만 살아남음)
        '인공지능 뉴스'  → 'dataset'  (남는 게 없음)
        '반도체 HBM'    → 'hbm'

    한글 제목은 거의 다 'dataset'으로 떨어져서 어차피 의미가 없었고, 영문
    제목은 제목을 조금만 바꿔도 식별자 모양이 달라졌다. 의미는 title 컬럼이
    들고 있으면 되고, 식별자는 유일하고 안정적이기만 하면 된다.

    읽을 수 있는 키가 필요하면 --dataset-id로 직접 지정한다 — 기존 18건이
    urn:naver:news_ai, urn:youtube:samsung_official 처럼 돼 있는 이유다.

    비정형은 데이터셋이 원천 객체 하나에 1:1로 대응하지 않는다. 같은 채널로
    데이터셋을 둘 만들 수 있으므로 채널 ID를 식별자로 쓰면 충돌한다. 그래서
    원천 키 자리에 **수집 단위 키**를 넣고, 원천 객체 키는 external_ids에
    보존한다(2026-10-28 협력기관 승인).

    origin(admin/user)은 식별자에 넣지 않는다. dataset_origin 컬럼이 이미
    구분하고 있어 중복이고, 등록 주체가 바뀌면 식별자까지 흔들린다.
    """
    ns = _SOURCE_META[source_type]["urn_namespace"]
    key = f"{_urn_key_prefix(source_type)}dataset"
    cur = conn.cursor()
    for _ in range(5):
        candidate = f"urn:{ns}:{key}_{secrets.token_hex(3)}"
        cur.execute("SELECT 1 FROM dcat_dataset WHERE dataset_id = %s", (candidate,))
        if cur.fetchone() is None:
            return candidate
    raise RuntimeError("dataset_id 채번 5회 시도 후에도 충돌 — 다시 시도해주세요")


def validate_dataset_id(dataset_id: str) -> str:
    """--dataset-id로 직접 지정한 값도 URN 형식이어야 한다."""
    if not URN_RE.match(dataset_id):
        raise SystemExit(f"--dataset-id는 urn:{{소스}}:{{수집단위키}} 형식이어야 합니다 "
                         f"(받은 값: {dataset_id!r})\n"
                         f"  예) urn:youtube:samsung_official")
    if len(dataset_id) > 100:
        raise SystemExit(f"--dataset-id가 스펙 상한 100자를 넘습니다({len(dataset_id)}자)")
    return dataset_id


def normalize_subject_key(terms) -> str:
    """수집 조건(검색어·카테고리)을 순서와 무관한 정규 문자열로 만든다.

        ['인공지능','AI','머신러닝','딥러닝']  →  'ai|딥러닝|머신러닝|인공지능'
        ['AI','인공지능','딥러닝','머신러닝']  →  동일 (순서 흡수)
        ['ai',' 인공지능 ','AI','딥러닝','머신러닝']  →  동일 (대소문자·공백·중복 흡수)

    공백 제거 → 소문자 → 중복 제거 → **코드포인트 정렬** → '|' 결합.

    ⚠️ 정렬은 반드시 코드포인트 순서여야 한다. SQL에서 같은 값을 만들 때는
    `COLLATE "C"`를 붙여야 파이썬 sorted()와 같아진다. DB 기본 콜레이션은
    한글을 영문보다 앞에 두어 결과가 달라진다.
        SQL 기본      : 딥러닝|머신러닝|인공지능|ai
        SQL COLLATE C : ai|딥러닝|머신러닝|인공지능   ← 파이썬과 같음
    """
    return "|".join(sorted({t.strip().lower() for t in terms if t and t.strip()}))


def subject_set_hash(terms) -> str:
    """정규화한 수집 조건의 sha256 앞 12자리. 'sha256-' 접두를 붙인다.

    sha1이 아니라 sha256을 쓰는 이유는 PostgreSQL에 sha256()이 내장돼 있어
    SQL에서도 같은 값을 만들 수 있기 때문이다(sha1은 내장이 아니다).

    **접두를 붙이는 이유**: external_ids의 협력기관 정의는 `adms:identifier` —
    "원천 포털이 데이터셋에 붙여 둔 고유번호"다. 이 해시는 어떤 기관도 발급한
    적이 없는 합성값이라 의미가 다르다. 동등성 비교라는 기능은 같지만 원천에
    조회되지 않는다. 접두가 없으면 `naver:news:3c639c929baf`가 네이버가 발급한
    ID처럼 보여 구분할 수 없다.
    """
    return "sha256-" + hashlib.sha256(
        normalize_subject_key(terms).encode("utf-8")).hexdigest()[:12]


def make_external_ids(source_type: str, subjects) -> str:
    """원천 객체 키를 '네임스페이스:값' 문자열 배열로 만든다(협력기관 정의 형식).

    같은 데이터셋이 다른 경로로 두 번 수집되면 이 값이 겹쳐 중복을 탐지할 수
    있게 하는 컬럼이다. dataset_id는 수집 단위 키라서 그 역할을 못 한다.

    source_type별로 넣는 값이 다르다.

    **video** — 채널 ID. 원천(YouTube)이 발급한 진짜 객체 키다.
        ["youtube:UCWwgaK7x0_FR1goeSRazfsQ"]
      개별 영상 ID는 넣지 않는다. 영상은 데이터셋의 원천 객체가 아니라 그 안의
      항목이고 meta_video가 이미 들고 있다.

    **그 외** — 수집 조건 집합의 해시.
        ["naver:news:sha256-3c639c929baf"]
      검색어·카테고리는 원천 객체가 아니라 우리가 정한 수집 조건이다. 개별
      값을 그대로 넣으면 조건 하나만 겹쳐도 서로 다른 데이터셋이 중복으로
      판정돼 오탐이 난다 — 실제로 shopping_insight와
      shopping_insight_advertiser는 카테고리 50000148을 공유한다.
      **집합 전체를 해시하면 완전히 같을 때만 겹친다.**

      정규화(정렬·중복제거·소문자) 덕분에 검색어를 적은 순서는 영향이 없다.
      원문은 subjects 컬럼에 그대로 남아 있어 해시는 언제든 다시 만들 수 있다.

    ⚠️ 기간(temporal_start/end)은 해시에 넣지 않는다. 같은 검색어를 기간만
    나눠 두 번 등록하면 두 데이터셋의 해시가 같아진다 — 의도적이다. 같은
    대상을 보고 있다는 사실이 드러나야 하고, 기간이 다르다는 건 temporal_*
    컬럼이 이미 말해준다.
    """
    if source_type == "video":
        if isinstance(subjects, dict):
            channels = subjects.get("channels") or []
            videos = subjects.get("videos") or []
        else:
            channels, videos = subjects or [], []
        ids = [f"youtube:{c}" for c in channels if c]
        # 큐레이션한 개별 영상은 집합 해시로 넣는다.
        # 채널 ID는 YouTube가 발급한 객체 키라 그대로 쓰지만, "이 영상들을 골랐다"는
        # 선택 자체는 우리가 정한 수집 조건이다. 영상 하나하나를 넣으면 한 편만
        # 겹쳐도 중복으로 오판되므로 news/blog와 같은 집합 해시 방식을 쓴다.
        #
        # 이 처리가 없으면 **채널 없이 영상만 고른 데이터셋은 external_ids가 통째로
        # 비어** 중복 판정 근거가 사라진다(2026-10-29 시나리오 점검에서 발견).
        if videos:
            ids.append(f"youtube:videoset:{subject_set_hash(videos)}")
        return json.dumps(ids)

    terms = subjects if isinstance(subjects, list) else []
    if not terms:
        return json.dumps([])
    ns = _SOURCE_META[source_type]["urn_namespace"]
    return json.dumps([f"{ns}:{source_type}:{subject_set_hash(terms)}"])


def resolve_keywords(args, subjects) -> list:
    """등록 시 keywords를 정한다.

    **사용자 입력이다.** 아이템에서 자동 추출한 값으로 대체하지 않는다 —
    meta_video.tags는 업로더 SEO 문구라 데이터셋 주제가 되지 못하고
    (["대항병원","사당대항병원","EBS명의", …]), 같은 카테고리를 다른 의도로 본
    데이터셋도 구별되지 않는다. 자세한 근거는
    docs/api/01_Dataset_Registration_Scenario.md §5.1 참조.

    news·blog만 검색어를 기본값으로 쓴다 — 검색어가 곧 주제인 경우가 많다.
    그 외는 필수다. 비어 있으면 그 데이터셋은 키워드 검색과 KEYWORD_OVERLAP
    관계 산출에서 통째로 빠진다(keywords에 GIN 인덱스가 걸려 있다).
    """
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        if kws:
            return kws
    if args.source_type in ("news", "blog") and isinstance(subjects, list):
        return [s for s in subjects if s]
    raise SystemExit(
        f"--keywords 가 필요합니다 (source_type={args.source_type}).\n"
        f"  데이터셋의 주제를 쉼표로 구분해 주세요. 예) --keywords \"위암,헬스케어,의료\"\n"
        f"  아이템 태그·카테고리명으로 대신 채우지 않습니다 — 그 값은 데이터셋의\n"
        f"  주제가 아니라 개별 항목을 설명하는 값이라, 의도가 다른 데이터셋이\n"
        f"  구별되지 않습니다."
    )


def register_discovery(args) -> str:
    meta = _SOURCE_META[args.source_type]
    if args.source_type == "video":
        # 채널 전체 발견(channels)과 관리자가 직접 고른 개별 영상(videos)을 한
        # 데이터셋 안에 섞을 수 있다(2026-07-28 확장, youtube_pipeline.py 참조).
        # news/blog는 검색어 배열이라 기존 평평한 리스트 형식 그대로 둔다.
        subjects = {
            "channels": args.subjects.split(",") if args.subjects else [],
            "videos": args.videos.split(",") if args.videos else [],
        }
    else:
        subjects = args.subjects.split(",")

    conn = get_conn()
    try:
        dataset_id = (validate_dataset_id(args.dataset_id) if args.dataset_id
                      else make_dataset_id(conn, args.source_type))
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dcat_dataset (
                dataset_id, title, description, publisher, source, source_type,
                subjects, accrual_periodicity, dataset_origin, owner_id, license,
                external_ids, keywords, party, landing_page, access_url, rights
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dataset_id, args.title, args.description,
                # 비정형은 원천(source)과 제공기관(publisher)이 같다 — 협력기관 합의 사항.
                # source는 NOT NULL이고 기본값이 없으므로 반드시 채워야 한다.
                meta["publisher"], meta["publisher"],
                args.source_type, json.dumps(subjects), args.periodicity,
                args.origin, args.owner_id, meta["license"],
                make_external_ids(args.source_type, subjects),
                json.dumps(resolve_keywords(args, subjects), ensure_ascii=False),
                PARTY_THIRD_PARTY,
                meta["landing_page"], meta["access_url"], meta["rights"],
            ),
        )
        cur.execute(
            """
            INSERT INTO data_registry (
                dataset_id, status, next_collect_at,
                pg_meta_table, pg_active_table, vec_collection
            ) VALUES (%s, 'pending', now(), %s, %s, 'dcat_dataset_vec')
            """,
            (dataset_id, meta["pg_meta_table"], meta["pg_active_table"]),
        )
        conn.commit()
        return dataset_id
    finally:
        conn.close()


def split_category_levels(category_name: str) -> tuple:
    """'패션의류>남성의류>정장' → ('패션의류', '남성의류', '정장', None).

    네이버 카테고리명은 '>'로 이어진 전체 경로다. cat_level1~4는 그 경로를 단계별로
    쪼갠 값으로, `idx_shopping_level1` 인덱스가 걸려 있어 대분류 집계·필터의 전제다.

    **등록 경로가 이 값을 채우지 않고 있었다**(2026-10-29 발견). 시드 데이터에만
    들어 있어 실제 등록으로 만든 행은 cat_level1~4가 전부 NULL이었다.
    """
    parts = [p.strip() for p in (category_name or "").split(">")]
    parts = [p for p in parts if p]
    return tuple((parts[i] if i < len(parts) else None) for i in range(4))


def register_declarative(args) -> str:
    meta = _SOURCE_META[args.source_type]
    categories = []
    for item in args.categories.split(","):
        cat_id, _, cat_name = item.partition(":")
        if not cat_id or not cat_name:
            raise ValueError(f"--categories 형식 오류: {item!r} (기대: 'id:name')")
        categories.append((cat_id.strip(), cat_name.strip()))

    conn = get_conn()
    try:
        dataset_id = (validate_dataset_id(args.dataset_id) if args.dataset_id
                      else make_dataset_id(conn, args.source_type))
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dcat_dataset (
                dataset_id, title, description, publisher, source, source_type,
                subjects, accrual_periodicity, item_count,
                dataset_origin, owner_id, license, temporal_start,
                external_ids, keywords, party, landing_page, access_url, rights,
                temporal_resolution
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dataset_id, args.title, args.description,
                # 비정형은 source = publisher (위 경로와 동일)
                meta["publisher"], meta["publisher"],
                args.source_type, json.dumps([cid for cid, _ in categories]), args.periodicity,
                len(categories), args.origin, args.owner_id, meta["license"], args.temporal_start,
                make_external_ids(args.source_type, [cid for cid, _ in categories]),
                json.dumps(resolve_keywords(args, [cid for cid, _ in categories]),
                           ensure_ascii=False),
                PARTY_THIRD_PARTY,
                meta["landing_page"], meta["access_url"], meta["rights"],
                meta["temporal_resolution"],
            ),
        )
        cur.execute(
            """
            INSERT INTO data_registry (
                dataset_id, status, next_collect_at,
                pg_meta_table, pg_active_table, vec_collection, item_count
            ) VALUES (%s, 'pending', now(), %s, %s, 'dcat_dataset_vec', %s)
            """,
            (dataset_id, meta["pg_meta_table"], meta["pg_active_table"], len(categories)),
        )

        # 첫 번째로 고른 카테고리를 자동으로 anchor 지정 (§4.3, shopping만 해당 컬럼 있음)
        table = meta["pg_meta_table"]
        for i, (cat_id, cat_name) in enumerate(categories):
            lv = split_category_levels(cat_name)
            if table == "meta_shopping_insight":
                cur.execute(
                    """
                    INSERT INTO meta_shopping_insight
                        (dataset_id, category_id, category_name, is_anchor,
                         cat_level1, cat_level2, cat_level3, cat_level4)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (dataset_id, cat_id, cat_name, i == 0, *lv),
                )
            else:  # meta_persona_insight — anchor 개념 없음
                cur.execute(
                    """
                    INSERT INTO meta_persona_insight
                        (dataset_id, category_id, category_name,
                         cat_level1, cat_level2, cat_level3, cat_level4)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (dataset_id, cat_id, cat_name, *lv),
                )
        conn.commit()
        return dataset_id
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_type", choices=sorted(DISCOVERY_TYPES | DECLARATIVE_TYPES))
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--origin", choices=["admin", "user"], default="admin")
    parser.add_argument("--owner-id", default=None, help="origin=user일 때만 의미 있음")
    parser.add_argument("--keywords",
                        help="데이터셋 주제, 쉼표 구분. 예) '위암,헬스케어,의료'. "
                             "news/blog는 생략 시 검색어로 채움, 그 외는 필수")
    parser.add_argument("--periodicity", default="P1D", help="ISO 8601 duration, 기본 P1D")
    parser.add_argument("--dataset-id", default=None, help="지정 안 하면 title로 자동 채번")
    parser.add_argument(
        "--subjects",
        help="발견형: video는 채널ID 콤마 구분 목록(채널 전체 발견용), "
             "news/blog는 검색어 콤마 구분 목록",
    )
    parser.add_argument(
        "--videos",
        help="video 전용: 채널과 별개로 관리자가 직접 고른 개별 video_id 콤마 구분 "
             "목록 — --subjects(채널)와 같이 써서 섞을 수 있고, --subjects 없이 "
             "이것만 줘도 됨(채널 전체 없이 개별 영상만 큐레이션하는 데이터셋)",
    )
    parser.add_argument("--categories", help="선언형: 'id:name,id:name' 콤마 구분 목록")
    parser.add_argument(
        "--temporal-start", default=None, metavar="YYYY-MM-DD",
        help="선언형(shopping_insight/persona_insight) 전용: 최초 수집 시 이 날짜부터 "
             "소급 수집한다(naver_shopping_pipeline.py 참조). 발견형은 아직 안 씀.",
    )
    args = parser.parse_args()

    if args.source_type in DISCOVERY_TYPES:
        if args.source_type == "video":
            if not args.subjects and not args.videos:
                parser.error("source_type='video'는 --subjects(채널) 또는 --videos(개별 영상) 중 하나는 필요")
        elif not args.subjects:
            parser.error(f"source_type={args.source_type!r}는 --subjects 필요")
        dataset_id = register_discovery(args)
    else:
        if not args.categories:
            parser.error(f"source_type={args.source_type!r}는 --categories 필요")
        dataset_id = register_declarative(args)

    print(f"등록 완료: {dataset_id}")
    print(f"수집 트리거: python -m src.main run {dataset_id}")


if __name__ == "__main__":
    main()
