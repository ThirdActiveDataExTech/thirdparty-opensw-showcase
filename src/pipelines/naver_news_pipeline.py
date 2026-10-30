"""Naver 뉴스 발견형 파이프라인 — §6.1과 같은 원리, "삭제 감지" 방식만 다르다.

YouTube는 채널의 전체 영상 목록을 한 번에 다 가져올 수 있어 "이번에 없으면
삭제"가 안전하다. 뉴스 검색 API는 그렇지 않다 — sort=date 슬라이딩 윈도우라
"검색 결과에 없음"이 몇 분 만에도 뒤집힐 수 있다(실측: 두 번 연속 실행 사이에
기존 기사 146건이 "검색 결과에 없음"으로 나왔는데, 직접 URL을 열어보니 그중
다수가 여전히 200 응답 — 명백한 오탐). 그래서 검색 결과 부재만으로 is_removed
처리하지 않고, 후보 기사의 URL을 **직접 재확인**한다 — 404/410으로 명확히
확인될 때만 삭제로 판정하고, 그 외(200/타임아웃/기타 오류)는 판단을 보류한다.
같은 원칙이 블로그(Phase 2 다음 항목)에도 그대로 적용돼야 한다.

댓글 수는 ADR-005로 검증된 방식대로 is_naver_hosted=TRUE 기사만 수집한다.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.collectors import naver_news_collector
from src.database import category, dcat
from src.database import meta_news
from src.database.db import get_conn
from src.embedding import sync as embedding_sync
from src.storage import jsonld_export, raw_export

AGENT = "naver_news_collector"
logger = logging.getLogger(__name__)


def _get_registry_status(dataset_id: str) -> str:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM data_registry WHERE dataset_id = %s", (dataset_id,))
        row = cur.fetchone()
        return row[0] if row else "pending"
    finally:
        conn.close()


def _current_item_count(dataset_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM meta_news WHERE dataset_id = %s", (dataset_id,))
        return cur.fetchone()[0]
    finally:
        conn.close()


def _current_row_count(dataset_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*) FROM active_meta_news a
            JOIN meta_news m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _collect_comment_stats(meta_id: int, article: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> None:
    if not article["is_naver_hosted"]:
        return
    stats = naver_news_collector.fetch_comment_stats(article["naver_oid"], article["naver_aid"])
    if stats is None:
        return
    delta = None
    if prev is not None and prev.get("comment_count") is not None and stats.get("comment_count") is not None:
        delta = stats["comment_count"] - prev["comment_count"]
    meta_news.insert_active_meta_news(
        meta_id, stats.get("comment_count"), stats.get("expose_count"), stats.get("reply_count"), delta,
    )


def _current_temporal_start(dataset_id: str) -> Optional[str]:
    """지금까지 수집된 항목 중 가장 이른 게시일. 데이터 없으면 None.

    dcat_dataset.temporal_start는 "수집 후 자동 갱신"으로 정의돼 있는데
    (sql/dcat_dataset.sql) 이 파이프라인은 갱신하지 않고 있었다 — 2026-10-28 발견.

    매 수집마다 다시 계산한다. 과거 게시물이 나중에 발견되면 시작일이 앞당겨져야
    하기 때문이다(쇼핑/Persona는 수집 범위가 고정이라 첫 수집 때만 계산한다).

    temporal_end는 두지 않는다 — NULL이 "현재 진행 중(open-ended)"을 뜻한다.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT MIN(published_at)::date FROM meta_news WHERE dataset_id = %s",
            (dataset_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def run(dataset_id: str, triggered_by: str) -> None:
    dataset = dcat.fetch_dcat_dataset(dataset_id)
    was_pending = _get_registry_status(dataset_id) == "pending"
    client_id = dcat.get_api_key(dataset_id, "naver_client_id")
    client_secret = dcat.get_api_key(dataset_id, "naver_client_secret")
    keywords = dataset["subjects"] if isinstance(dataset["subjects"], list) else json.loads(dataset["subjects"])
    started_at = datetime.now(timezone.utc)

    try:
        existing = meta_news.get_existing_articles(dataset_id)
        remote_urls = set()
        processed_this_run = set()  # 여러 검색어에 같은 기사가 매칭돼도 1회만 처리
        new_count, updated_count, removed_count = 0, 0, 0

        for keyword in keywords:
            for item in naver_news_collector.search_all(client_id, client_secret, keyword):
                article = naver_news_collector.normalize_article(item, keyword)
                url = article["article_url"]
                remote_urls.add(url)

                if url in processed_this_run:
                    continue  # 이미 이번 실행에서 다른 검색어로 처리됨 — 중복 API 호출 방지
                processed_this_run.add(url)

                if url not in existing:
                    content = naver_news_collector.fetch_article_content(url)
                    meta_id = meta_news.insert_meta_news(dataset_id, article, content)
                    _collect_comment_stats(meta_id, article, prev=None)
                    if content:
                        try:
                            raw_export.write_article_content(dataset_id, "news", meta_id, content)
                        except Exception as e:
                            logger.warning(f"raw 본문 업로드 실패 (meta_id={meta_id}): {e}")
                    # 같은 기사가 다른 검색어에서도 매칭될 수 있어, 이번 실행 중 발견한
                    # 것도 바로 existing에 반영 — 안 하면 두 번째 매칭 때 중복 INSERT 시도함
                    existing[url] = {
                        "id": meta_id, "published_at": article["published_at"],
                        "is_naver_hosted": article["is_naver_hosted"],
                        "naver_oid": article["naver_oid"], "naver_aid": article["naver_aid"],
                        "is_removed": False,
                    }
                    new_count += 1
                else:
                    meta_id = existing[url]["id"]
                    meta_news.clear_removed_flag(meta_id)
                    prev = meta_news.get_latest_active_meta(meta_id)
                    _collect_comment_stats(meta_id, article, prev)
                    updated_count += 1

        # 검색 결과에 없는 기존 기사는 "삭제 후보"일 뿐 — URL을 직접 재확인해서
        # 404/410으로 명확히 확인된 것만 삭제 처리 (윈도우 부재 자체는 근거로 안 씀)
        for url, info in existing.items():
            if url in remote_urls or info["is_removed"]:
                continue
            still_exists = naver_news_collector.check_article_still_exists(url)
            if still_exists is False:
                meta_news.mark_removed(info["id"], removed_at=datetime.now(timezone.utc))
                removed_count += 1

        ended_at = datetime.now(timezone.utc)

        dcat.insert_dcat_provenance(
            dataset_id, activity_type="initial" if was_pending else "update",
            agent=AGENT, triggered_by=triggered_by,
            started_at=started_at, ended_at=ended_at, status="success",
            rows_affected=new_count + updated_count,
            params={"keywords": keywords},
            notes=f"신규 {new_count} / 갱신 {updated_count} / 삭제감지 {removed_count}",
        )
        dcat.update_data_registry(
            dataset_id,
            status="active",
            item_count=_current_item_count(dataset_id),
            row_count=_current_row_count(dataset_id),
            temporal_start=_current_temporal_start(dataset_id),
            last_collected_at=ended_at,
            next_collect_at=ended_at + dcat.parse_iso8601_duration_to_timedelta(dataset["accrual_periodicity"]),
            last_error=None,
        )

        try:
            s3_raw_prefix, s3_jsonld_prefix = jsonld_export.export_dataset(dataset_id)
            dcat.update_data_registry(dataset_id, s3_raw_prefix=s3_raw_prefix, s3_jsonld_prefix=s3_jsonld_prefix)
        except Exception as e:
            logger.warning(f"S3 export 실패, 수집 자체는 성공 처리: {e}")

        # category(공통 분류) 부여 — theme 집계 뒤에 해야 theme을 근거로 쓸 수 있다.
        # 협력기관 분류표(대분류 7 / 중분류 76) 안에서 임베딩 최근접으로 고른다.
        # ⚠️ 품질이 낮다(Top-1 3/8). 비워 두면 포털 전체 필터링이 성립하지 않아
        #    틀리더라도 일단 부여하고, 로컬 sLLM이 생기면 대체한다.
        #    docs/database/column_fill_matrix.md §9
        try:
            cats = category.sync_category(dataset_id)
            if cats:
                logger.info("category 부여: %s", ", ".join(cats))
        except Exception as e:
            logger.warning(f"category 부여 실패, 수집 자체는 성공 처리: {e}")

        # 임베딩 동기화 — 바뀐 항목만 다시 만든다(src/embedding/sync.py).
        # 2026-10-28 편입. 그 전에는 scripts/embed_*.py 수동 실행이었고 실데이터에
        # 한 번도 돌지 않아 임베딩이 사실상 0건이었다. 벡터 검색과 관계 산출이
        # 여기에 의존한다.
        #
        # S3 export와 같은 이유로 실패해도 수집은 성공 처리한다 — 수집 데이터는
        # 이미 DB에 들어갔고, 임베딩은 다음 수집 때 다시 시도된다(증분이므로
        # 밀린 분이 자동으로 따라잡힌다).
        try:
            stat = embedding_sync.sync_for_dataset("news", dataset_id)
            if stat["items"]:
                logger.info(
                    "임베딩 %d건(청크 %d개) 생성 — 검사 %d건",
                    stat["items"], stat["chunks"], stat["checked"],
                )
        except Exception as e:
            logger.warning(f"임베딩 실패, 수집 자체는 성공 처리: {e}")
    except Exception as e:
        ended_at = datetime.now(timezone.utc)
        dcat.insert_dcat_provenance(
            dataset_id, activity_type="initial" if was_pending else "update",
            agent=AGENT, triggered_by=triggered_by,
            started_at=started_at, ended_at=ended_at, status="failure",
            error_message=str(e),
        )
        dcat.update_data_registry(
            dataset_id, status="error", last_error=str(e),
            next_collect_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        raise
