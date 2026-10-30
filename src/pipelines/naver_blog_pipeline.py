"""Naver 블로그 발견형 파이프라인 — 뉴스와 같은 원리 + 반응 수(ADR-006) 수집.

뉴스 파이프라인 개발 중 확립한 두 원칙을 그대로 따른다:
  1) 검색 API는 sort=date 슬라이딩 윈도우라 "검색 결과 부재"만으로 삭제 판정하지
     않는다 — URL을 직접 재확인(HEAD)해서 404/410 확정시만 is_removed 처리
     (04_Collection_Pipeline_Operations.md §6.1 참조)
  2) 같은 게시물이 여러 검색어에 매칭될 수 있어 실행 중(run 내) 처리 여부를
     추적해서 중복 INSERT·중복 API 호출을 막는다

반응 수(공감 등)는 ADR-006으로 검증된 platform='naver' 게시물만 수집한다.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.collectors import naver_blog_collector
from src.database import category, dcat
from src.database import meta_blog
from src.database.db import get_conn
from src.embedding import sync as embedding_sync
from src.storage import jsonld_export, raw_export

AGENT = "naver_blog_collector"
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
        cur.execute("SELECT count(*) FROM meta_blog WHERE dataset_id = %s", (dataset_id,))
        return cur.fetchone()[0]
    finally:
        conn.close()


def _current_row_count(dataset_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*) FROM active_meta_blog a
            JOIN meta_blog m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _collect_reaction_stats(meta_id: int, post: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> None:
    """반응 수(좋아요 등)를 모아 active_meta_blog에 넣는다.

    **실패해도 예외를 올리지 않는다.** 반응 수는 부가 지표이고 게시물 본문은 이미
    meta_blog에 들어간 상태다. 2026-10-29 점검에서 blog.like.naver.com 타임아웃
    하나가 데이터셋 수집 전체를 실패시키는 것을 확인했다 — 게시물 수백 건을 다 모아
    놓고 마지막에 전부 버리는 꼴이었다.

    재시도는 with_retry가 한다(src/common/retry.py). 그걸 넘어서도 실패하면 이번
    회차의 그 게시물만 반응 수가 없고, 다음 수집에서 다시 시도된다.
    """
    if post["platform"] != "naver" or not post["blog_id"] or not post["log_no"]:
        return
    try:
        stats = naver_blog_collector.fetch_reaction_stats(post["blog_id"], post["log_no"])
    except Exception as e:
        logger.warning(
            "반응 수 수집 실패 (blog_id=%s, log_no=%s): %s — 게시물 자체는 유지",
            post["blog_id"], post["log_no"], e,
        )
        return
    if stats is None:
        return
    delta = None
    if prev is not None and prev.get("reaction_count") is not None:
        delta = stats["reaction_count"] - prev["reaction_count"]
    meta_blog.insert_active_meta_blog(
        meta_id, stats["reaction_count"], stats["reaction_breakdown"], delta,
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
            "SELECT MIN(published_at)::date FROM meta_blog WHERE dataset_id = %s",
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
        existing = meta_blog.get_existing_posts(dataset_id)
        remote_urls = set()
        processed_this_run = set()
        new_count, updated_count, removed_count = 0, 0, 0

        for keyword in keywords:
            for item in naver_blog_collector.search_all(client_id, client_secret, keyword):
                post = naver_blog_collector.normalize_post(item, keyword)
                url = post["post_url"]
                remote_urls.add(url)

                if url in processed_this_run:
                    continue
                processed_this_run.add(url)

                if url not in existing:
                    content = naver_blog_collector.fetch_post_content(
                        url, post["platform"], post["blog_id"], post["log_no"]
                    )
                    meta_id = meta_blog.insert_meta_blog(dataset_id, post, content)
                    _collect_reaction_stats(meta_id, post, prev=None)
                    if content:
                        try:
                            raw_export.write_article_content(dataset_id, "blog", meta_id, content)
                        except Exception as e:
                            logger.warning(f"raw 본문 업로드 실패 (meta_id={meta_id}): {e}")
                    existing[url] = {
                        "id": meta_id, "platform": post["platform"],
                        "blog_id": post["blog_id"], "log_no": post["log_no"],
                        "is_removed": False,
                    }
                    new_count += 1
                else:
                    meta_id = existing[url]["id"]
                    meta_blog.clear_removed_flag(meta_id)
                    prev = meta_blog.get_latest_active_meta(meta_id)
                    _collect_reaction_stats(meta_id, post, prev)
                    updated_count += 1

        for url, info in existing.items():
            if url in remote_urls or info["is_removed"]:
                continue
            still_exists = naver_blog_collector.check_post_still_exists(url)
            if still_exists is False:
                meta_blog.mark_removed(info["id"], removed_at=datetime.now(timezone.utc))
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
            stat = embedding_sync.sync_for_dataset("blog", dataset_id)
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
