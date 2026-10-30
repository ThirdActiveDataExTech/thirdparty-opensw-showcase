"""source_type별 JSON-LD 생성 + 업로드 — architecture/05_Object_Storage_Export.md §3, §7.3.

DB의 "지금 전체 상태"를 매번 다시 읽어 통째로 재생성한다(§5 확정) — 이 파일의 _build_*
함수들은 naver_shopping_pipeline.py의 _current_row_count처럼 이 모듈 전용 SELECT를
직접 작성한다(database/meta_*.py에 범용 전체조회 함수를 추가로 늘리지 않는 기존 관례를
따름). shopping/persona는 §3.3 확정(참조 방식)에 따라 전체 시계열은 CSV로, JSON-LD엔
최신 스냅샷만 넣는다 — 그래서 이 두 소스 타입의 _build_*는 raw_export.write_declarative_csv
호출까지 같이 한다(호출부는 파이프라인 쪽에 CSV 쓰기를 별도로 추가하지 않아도 됨).
"""

from typing import Any, Dict, List, Tuple

from src.database.db import get_conn
from src.storage import raw_export, s3_client

_CONTEXT = {
    "dct": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "schema": "https://schema.org/",
    "adms": "http://www.w3.org/ns/adms#",
    "mi": "https://metadata-ingestion.internal/ns#",
}


def _fetch_dataset_context(dataset_id: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.dataset_id, d.source_type, d.title, d.description, d.publisher,
                   d.license, d.keywords, d.external_ids,
                   d.accrual_periodicity, d.temporal_start, d.temporal_end,
                   r.status, r.item_count, r.row_count, r.last_collected_at, r.next_collect_at
            FROM dcat_dataset d
            JOIN data_registry r ON r.dataset_id = d.dataset_id
            WHERE d.dataset_id = %s
            """,
            (dataset_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"dcat_dataset/data_registry에 dataset_id={dataset_id!r} 없음")
        columns = [c[0] for c in cur.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def _iso(value):
    return value.isoformat() if value is not None else None


def _base_jsonld(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "@context": _CONTEXT,
        # dataset_id 자체가 URN이므로 그대로 @id로 쓴다(URN은 유효한 IRI).
        # 전환 전에는 mi:dataset/{slug} CURIE였다 — 이제는 그 안에 콜론이 섞여
        # mi:dataset/urn:naver:news_ai 같은 어색한 값이 된다. 2026-10-28 변경.
        "@id": ctx["dataset_id"],
        "@type": "dcat:Dataset",
        "dct:identifier": ctx["dataset_id"],
        "dct:title": ctx["title"],
        "dct:description": ctx["description"],
        "dct:publisher": ctx["publisher"],
        "dct:license": ctx["license"],
        "dct:accrualPeriodicity": ctx["accrual_periodicity"],
        "dcat:keyword": ctx["keywords"] or [],
        # 외부 식별자 — 협력기관 정형과 같은 컬럼·같은 '네임스페이스:값' 형식이다.
        # 두 종류가 섞여 있고, 값 자체로 구분된다.
        #   youtube:UCWwg...            원천(YouTube)이 발급한 채널 ID
        #   naver:news:sha256-3c639c...  우리가 계산한 수집 조건 집합 해시
        #   legacy:naver_news_ai         URN 전환 전 우리 식별자
        # adms:identifier의 본래 뜻은 "어떤 기관이 발급한 식별자"라서 해시는
        # 엄밀히는 그 범주가 아니다. 그래도 같은 속성으로 내보내는 이유는 형식을
        # 협력기관과 맞춰야 받는 쪽이 한 가지 규칙으로 기록할 수 있기 때문이고,
        # sha256- 접두가 있어 합성값인지는 값만 보고 가려낼 수 있다.
        "adms:identifier": ctx["external_ids"] or [],
        "mi:temporalStart": _iso(ctx["temporal_start"]),
        "mi:temporalEnd": _iso(ctx["temporal_end"]),
        "mi:activeMetadata": {
            "status": ctx["status"],
            "itemCount": ctx["item_count"],
            "rowCount": ctx["row_count"],
            "lastCollectedAt": _iso(ctx["last_collected_at"]),
            "nextCollectAt": _iso(ctx["next_collect_at"]),
        },
    }


def _build_video(dataset_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, video_id, title, description, published_at, channel_id,
                   channel_title, tags, is_removed, has_transcript
            FROM meta_video WHERE dataset_id = %s ORDER BY id
            """,
            (dataset_id,),
        )
        cols = [c[0] for c in cur.description]
        videos = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT a.meta_id, a.collected_at, a.view_count, a.like_count, a.comment_count,
                   a.delta_views, a.delta_likes, a.delta_comments
            FROM active_meta_video a
            JOIN meta_video m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            ORDER BY a.meta_id, a.collected_at
            """,
            (dataset_id,),
        )
        active_by_meta: Dict[int, List[Dict[str, Any]]] = {}
        for meta_id, collected_at, vc, lc, cc, dv, dl, dc in cur.fetchall():
            active_by_meta.setdefault(meta_id, []).append(
                {
                    "collectedAt": _iso(collected_at),
                    "viewCount": vc,
                    "likeCount": lc,
                    "commentCount": cc,
                    "deltaViews": dv,
                    "deltaLikes": dl,
                    "deltaComments": dc,
                }
            )
    finally:
        conn.close()

    items = []
    for v in videos:
        item = {
            "@type": "schema:VideoObject",
            "@id": f"https://youtube.com/watch?v={v['video_id']}",
            "schema:identifier": v["video_id"],
            "schema:name": v["title"],
            "schema:description": v["description"],
            "schema:uploadDate": _iso(v["published_at"]),
            "schema:author": {
                "@type": "schema:Organization",
                "schema:name": v["channel_title"],
                "schema:identifier": v["channel_id"],
            },
            "schema:keywords": v["tags"] or [],
            "mi:isRemoved": v["is_removed"],
            "mi:activeMetadata": active_by_meta.get(v["id"], []),
        }
        if v["has_transcript"]:
            item["mi:transcriptRef"] = f"raw/video/{dataset_id}/{v['video_id']}.json"
        items.append(item)

    doc = _base_jsonld(ctx)
    doc["mi:items"] = items
    return doc


def _build_news(dataset_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, article_url, title, description, publisher, published_at,
                   search_keyword, is_removed, has_content
            FROM meta_news WHERE dataset_id = %s ORDER BY id
            """,
            (dataset_id,),
        )
        cols = [c[0] for c in cur.description]
        articles = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT a.meta_id, a.collected_at, a.comment_count, a.expose_count,
                   a.reply_count, a.delta_comments
            FROM active_meta_news a
            JOIN meta_news m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            ORDER BY a.meta_id, a.collected_at
            """,
            (dataset_id,),
        )
        active_by_meta: Dict[int, List[Dict[str, Any]]] = {}
        for meta_id, collected_at, cc, ec, rc, dc in cur.fetchall():
            active_by_meta.setdefault(meta_id, []).append(
                {
                    "collectedAt": _iso(collected_at),
                    "commentCount": cc,
                    "exposeCount": ec,
                    "replyCount": rc,
                    "deltaComments": dc,
                }
            )
    finally:
        conn.close()

    items = []
    for a in articles:
        item = {
            "@type": "schema:NewsArticle",
            "@id": a["article_url"],
            "schema:headline": a["title"],
            "schema:abstract": a["description"],
            "schema:publisher": a["publisher"],
            "schema:datePublished": _iso(a["published_at"]),
            "mi:searchKeyword": a["search_keyword"],
            "mi:isRemoved": a["is_removed"],
            "mi:activeMetadata": active_by_meta.get(a["id"], []),
        }
        if a["has_content"]:
            item["mi:contentRef"] = f"raw/news/{dataset_id}/{a['id']}.txt"
        items.append(item)

    doc = _base_jsonld(ctx)
    doc["mi:items"] = items
    return doc


def _build_blog(dataset_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, post_url, title, description, blogger_name, published_at,
                   search_keyword, is_removed, has_content, platform
            FROM meta_blog WHERE dataset_id = %s ORDER BY id
            """,
            (dataset_id,),
        )
        cols = [c[0] for c in cur.description]
        posts = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT a.meta_id, a.collected_at, a.reaction_count, a.reaction_breakdown, a.delta_reactions
            FROM active_meta_blog a
            JOIN meta_blog m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            ORDER BY a.meta_id, a.collected_at
            """,
            (dataset_id,),
        )
        active_by_meta: Dict[int, List[Dict[str, Any]]] = {}
        for meta_id, collected_at, rc, breakdown, dr in cur.fetchall():
            active_by_meta.setdefault(meta_id, []).append(
                {
                    "collectedAt": _iso(collected_at),
                    "reactionCount": rc,
                    "reactionBreakdown": breakdown,
                    "deltaReactions": dr,
                }
            )
    finally:
        conn.close()

    items = []
    for p in posts:
        item = {
            "@type": "schema:BlogPosting",
            "@id": p["post_url"],
            "schema:headline": p["title"],
            "schema:abstract": p["description"],
            "schema:author": {"@type": "schema:Person", "schema:name": p["blogger_name"]},
            "schema:datePublished": _iso(p["published_at"]),
            "mi:searchKeyword": p["search_keyword"],
            "mi:platform": p["platform"],
            "mi:isRemoved": p["is_removed"],
            "mi:activeMetadata": active_by_meta.get(p["id"], []),
        }
        if p["has_content"]:
            item["mi:contentRef"] = f"raw/blog/{dataset_id}/{p['id']}.txt"
        items.append(item)

    doc = _base_jsonld(ctx)
    doc["mi:items"] = items
    return doc


def _build_shopping(dataset_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.id, m.category_id, m.category_name, m.is_anchor,
                   a.period, a.gender, a.age, a.raw_ratio, a.scale_factor, a.pseudo_volume
            FROM meta_shopping_insight m
            LEFT JOIN active_meta_shopping_insight a ON a.meta_id = m.id
            WHERE m.dataset_id = %s
            ORDER BY m.id, a.period, a.gender, a.age
            """,
            (dataset_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    categories: Dict[int, Dict[str, Any]] = {}
    csv_rows: List[Dict[str, Any]] = []
    for meta_id, cat_id, cat_name, is_anchor, period, gender, age, raw_ratio, scale_factor, pv in rows:
        cat = categories.setdefault(
            meta_id,
            {
                "categoryId": cat_id,
                "categoryName": cat_name,
                "isAnchor": is_anchor,
                "periodStart": None,
                "periodEnd": None,
                "pointCount": 0,
                "latestPeriod": None,
                "latestRows": [],
            },
        )
        if period is None:
            continue
        cat["pointCount"] += 1
        cat["periodStart"] = period if cat["periodStart"] is None else min(cat["periodStart"], period)
        cat["periodEnd"] = period if cat["periodEnd"] is None else max(cat["periodEnd"], period)
        row = {"period": period.isoformat(), "gender": gender, "age": age, "pseudoVolume": pv, "scaleFactor": scale_factor}
        if cat["latestPeriod"] is None or period > cat["latestPeriod"]:
            cat["latestPeriod"] = period
            cat["latestRows"] = [row]
        elif period == cat["latestPeriod"]:
            cat["latestRows"].append(row)
        csv_rows.append(
            {
                "category_id": cat_id,
                "category_name": cat_name,
                "period": period.isoformat(),
                "gender": gender,
                "age": age,
                "raw_ratio": raw_ratio,
                "scale_factor": scale_factor,
                "pseudo_volume": pv,
            }
        )

    raw_export.write_declarative_csv(dataset_id, "shopping_insight", csv_rows)

    items = []
    for cat in categories.values():
        items.append(
            {
                "@type": "mi:Category",
                "mi:categoryId": cat["categoryId"],
                "mi:categoryName": cat["categoryName"],
                "mi:isAnchor": cat["isAnchor"],
                "mi:timeSeriesRef": f"raw/shopping_insight/{dataset_id}/{dataset_id}.csv",
                "mi:timeSeriesSummary": {
                    "periodStart": _iso(cat["periodStart"]),
                    "periodEnd": _iso(cat["periodEnd"]),
                    "pointCount": cat["pointCount"],
                },
                "mi:latestSnapshot": cat["latestRows"],
            }
        )

    doc = _base_jsonld(ctx)
    doc["mi:items"] = items
    return doc


def _build_persona(dataset_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.id, m.category_id, m.category_name,
                   a.period, a.gender, a.age, a.gender_ratio, a.age_ratio,
                   a.gender_scale, a.age_scale, a.gender_pv, a.age_pv, a.persona_index
            FROM meta_persona_insight m
            LEFT JOIN active_meta_persona_insight a ON a.meta_id = m.id
            WHERE m.dataset_id = %s
            ORDER BY m.id, a.period, a.gender, a.age
            """,
            (dataset_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    categories: Dict[int, Dict[str, Any]] = {}
    csv_rows: List[Dict[str, Any]] = []
    for meta_id, cat_id, cat_name, period, gender, age, gr, ar, gs, ags, gpv, apv, pi in rows:
        cat = categories.setdefault(
            meta_id,
            {
                "categoryId": cat_id,
                "categoryName": cat_name,
                "periodStart": None,
                "periodEnd": None,
                "pointCount": 0,
                "latestPeriod": None,
                "latestRows": [],
            },
        )
        if period is None:
            continue
        cat["pointCount"] += 1
        cat["periodStart"] = period if cat["periodStart"] is None else min(cat["periodStart"], period)
        cat["periodEnd"] = period if cat["periodEnd"] is None else max(cat["periodEnd"], period)
        row = {"period": period.isoformat(), "gender": gender, "age": age, "personaIndex": pi, "genderPv": gpv, "agePv": apv}
        if cat["latestPeriod"] is None or period > cat["latestPeriod"]:
            cat["latestPeriod"] = period
            cat["latestRows"] = [row]
        elif period == cat["latestPeriod"]:
            cat["latestRows"].append(row)
        csv_rows.append(
            {
                "category_id": cat_id,
                "category_name": cat_name,
                "period": period.isoformat(),
                "gender": gender,
                "age": age,
                "gender_ratio": gr,
                "age_ratio": ar,
                "gender_scale": gs,
                "age_scale": ags,
                "gender_pv": gpv,
                "age_pv": apv,
                "persona_index": pi,
            }
        )

    raw_export.write_declarative_csv(dataset_id, "persona_insight", csv_rows)

    items = []
    for cat in categories.values():
        items.append(
            {
                "@type": "mi:Category",
                "mi:categoryId": cat["categoryId"],
                "mi:categoryName": cat["categoryName"],
                "mi:timeSeriesRef": f"raw/persona_insight/{dataset_id}/{dataset_id}.csv",
                "mi:timeSeriesSummary": {
                    "periodStart": _iso(cat["periodStart"]),
                    "periodEnd": _iso(cat["periodEnd"]),
                    "pointCount": cat["pointCount"],
                },
                "mi:latestSnapshot": cat["latestRows"],
            }
        )

    doc = _base_jsonld(ctx)
    doc["mi:items"] = items
    return doc


_BUILDERS = {
    "video": _build_video,
    "news": _build_news,
    "blog": _build_blog,
    "shopping_insight": _build_shopping,
    "persona_insight": _build_persona,
}


def export_dataset(dataset_id: str) -> Tuple[str, str]:
    """DB 현재 상태를 통째로 다시 읽어 JSON-LD(+선언형은 CSV도) 재생성/업로드.

    반환값 = (s3_raw_prefix, s3_jsonld_prefix) — data_registry 갱신용.
    """
    ctx = _fetch_dataset_context(dataset_id)
    source_type = ctx["source_type"]
    builder = _BUILDERS.get(source_type)
    if builder is None:
        raise ValueError(f"알 수 없는 source_type: {source_type}")

    doc = builder(dataset_id, ctx)
    # 경로에는 dataset_id 대신 storage_key()를 쓴다 — URN의 콜론을 키에 넣지
    # 않으면서 전환 전 경로를 그대로 유지한다(s3_client.storage_key 참조).
    key = s3_client.storage_key(dataset_id)
    jsonld_key = f"jsonld/{source_type}/{key}/{key}.jsonld"
    s3_client.upload_json(jsonld_key, doc)

    return f"raw/{source_type}/{key}/", f"jsonld/{source_type}/{key}/"
