"""Naver Persona 선언형 파이프라인 — shopping과 같은 §6.2 원리, 다른 보정 방식.

shopping_insight와 마찬가지로 카테고리 목록은 등록 시점에 고정되고 Collector가
바꾸지 않는다. 차이는 API 구조 — persona는 카테고리당 성별/연령 API를 독립
호출하고(anchor·배칭 없음), gender/age 시리즈를 stacking한 median으로 scale을
보정한 뒤 persona_index = gender_pv × age_pv (독립 가정)를 12조합(2성별×6연령)
전부 계산해 저장한다. 레거시 3amd/naver_persona.py 포팅.

날짜 범위는 shopping과 동일하게 "DB 마지막 저장 날짜 - OVERLAP_DAYS부터 어제까지"를
매번 다시 가져온다(2026-07-28, naver_shopping_pipeline.py 상단 주석 참조 — 하루씩만
가져오면 inter_scale 계산에 쓸 겹치는 날짜가 절대 안 생겨서 gender_scale/age_scale이
항상 1.0으로 죽어있던 버그의 수정). 최초 수집 시 `dcat_dataset.temporal_start`가
지정돼 있으면 그 날짜부터 소급 수집하는 것도 shopping과 동일.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.collectors import naver_datalab_scale, naver_persona_collector
from src.database import category, dcat, meta_persona_insight, theme
from src.database.db import get_conn
from src.embedding import sync as embedding_sync
from src.storage import jsonld_export

AGENT = "naver_persona_collector"
logger = logging.getLogger(__name__)
GENDER_GROUPS = ["m", "f"]
AGE_GROUPS = ["10", "20", "30", "40", "50", "60"]
OVERLAP_DAYS = 14


def _get_registry_status(dataset_id: str) -> str:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM data_registry WHERE dataset_id = %s", (dataset_id,))
        row = cur.fetchone()
        return row[0] if row else "pending"
    finally:
        conn.close()


def _current_row_count(dataset_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*) FROM active_meta_persona_insight a
            JOIN meta_persona_insight m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _flatten(parsed: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """{period: {group: ratio}} → {'period|group': ratio} — 스택 median 계산용 평탄화."""
    return {f"{period}|{group}": ratio for period, groups in parsed.items() for group, ratio in groups.items()}


def _compute_fetch_range(dataset_id: str, dataset: Dict[str, Any]) -> Tuple[str, str]:
    end_date = date.today() - timedelta(days=1)
    last_period = meta_persona_insight.get_last_period(dataset_id)
    if last_period is None:
        desired_start = dataset.get("temporal_start")
        start_date = desired_start if desired_start is not None else end_date - timedelta(days=OVERLAP_DAYS)
    else:
        start_date = min(date.fromisoformat(last_period) - timedelta(days=OVERLAP_DAYS), end_date)
    return start_date.isoformat(), end_date.isoformat()


def _current_temporal_start(dataset_id: str) -> Optional[str]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MIN(a.period) FROM active_meta_persona_insight a
            JOIN meta_persona_insight m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        row = cur.fetchone()
        return row[0].isoformat() if row and row[0] else None
    finally:
        conn.close()


def run(dataset_id: str, triggered_by: str) -> None:
    dataset = dcat.fetch_dcat_dataset(dataset_id)
    was_pending = _get_registry_status(dataset_id) == "pending"
    client_id = dcat.get_api_key(dataset_id, "naver_client_id")
    client_secret = dcat.get_api_key(dataset_id, "naver_client_secret")

    categories = meta_persona_insight.get_meta_persona_insight_rows(dataset_id)
    start_date, end_date = _compute_fetch_range(dataset_id, dataset)
    started_at = datetime.now(timezone.utc)
    rows_written = 0

    try:
        for cat in categories:
            rows_written += _collect_one_category(cat, start_date, end_date, client_id, client_secret)

        ended_at = datetime.now(timezone.utc)
        dcat.insert_dcat_provenance(
            dataset_id, activity_type="initial" if was_pending else "update",
            agent=AGENT, triggered_by=triggered_by,
            started_at=started_at, ended_at=ended_at, status="success",
            rows_affected=rows_written,
            params={"start_date": start_date, "end_date": end_date, "categories": len(categories)},
        )

        temporal_start_update: Dict[str, Any] = {}
        if was_pending:
            actual_start = _current_temporal_start(dataset_id)
            if actual_start is not None:
                temporal_start_update["temporal_start"] = actual_start
                dcat.update_dcat_dataset(dataset_id, temporal_start=actual_start)

        dcat.update_data_registry(
            dataset_id,
            status="active",
            item_count=len(categories),
            row_count=_current_row_count(dataset_id),
            last_collected_at=ended_at,
            **temporal_start_update,
            next_collect_at=ended_at + dcat.parse_iso8601_duration_to_timedelta(dataset["accrual_periodicity"]),
            last_error=None,
        )

        try:
            s3_raw_prefix, s3_jsonld_prefix = jsonld_export.export_dataset(dataset_id)
            dcat.update_data_registry(dataset_id, s3_raw_prefix=s3_raw_prefix, s3_jsonld_prefix=s3_jsonld_prefix)
        except Exception as e:
            logger.warning(f"S3 export 실패, 수집 자체는 성공 처리: {e}")

        # theme(원천 분류 원문) 집계 — 수집 결과에서 다시 계산한다.
        # video는 YouTube 카테고리+위키 주제, 선언형은 쇼핑 카테고리 대분류.
        # news/blog는 원천이 분류를 주지 않아 이 단계가 없다(src/database/theme.py).
        try:
            themes = theme.sync_theme(dataset_id, "persona_insight")
            if themes:
                logger.info("theme %d종 반영: %s", len(themes), ", ".join(themes[:4]))
        except Exception as e:
            logger.warning(f"theme 집계 실패, 수집 자체는 성공 처리: {e}")

        # category(공통 분류) 부여 — theme 집계 뒤에 해야 theme을 근거로 쓸 수 있다.
        # 공통 분류표(대분류 7 / 중분류 76) 안에서 임베딩 최근접으로 고른다.
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
            stat = embedding_sync.sync_for_dataset("persona_insight", dataset_id)
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


def _collect_one_category(
    cat: Dict[str, Any], start_date: str, end_date: str, client_id: str, client_secret: str
) -> int:
    gender_data = naver_persona_collector.fetch_ratios(
        naver_persona_collector.GENDER_API_URL, client_id, client_secret,
        start_date, end_date, "date", cat["category_id"],
    )
    age_data = naver_persona_collector.fetch_ratios(
        naver_persona_collector.AGE_API_URL, client_id, client_secret,
        start_date, end_date, "date", cat["category_id"],
    )
    gender_parsed = naver_persona_collector.parse_persona_response(gender_data) if gender_data else {}
    age_parsed = naver_persona_collector.parse_persona_response(age_data) if age_data else {}

    periods = list(set(gender_parsed.keys()) | set(age_parsed.keys()))
    existing_gender = meta_persona_insight.get_existing_gender_ratios(cat["id"], periods)
    existing_age = meta_persona_insight.get_existing_age_ratios(cat["id"], periods)
    existing_gender_flat = {f"{p}|{g}": r for (p, g), r in existing_gender.items()}
    existing_age_flat = {f"{p}|{a}": r for (p, a), r in existing_age.items()}

    gender_scale = naver_datalab_scale.compute_inter_scale(existing_gender_flat, _flatten(gender_parsed))
    age_scale = naver_datalab_scale.compute_inter_scale(existing_age_flat, _flatten(age_parsed))

    rows_written = 0
    for period in set(gender_parsed.keys()) & set(age_parsed.keys()):
        g_groups = gender_parsed[period]
        a_groups = age_parsed[period]
        for gender in GENDER_GROUPS:
            g_ratio = g_groups.get(gender)
            g_pv = g_ratio * gender_scale if g_ratio is not None else None
            for age in AGE_GROUPS:
                a_ratio = a_groups.get(age)
                a_pv = a_ratio * age_scale if a_ratio is not None else None
                score = g_pv * a_pv if (g_pv is not None and a_pv is not None) else None
                meta_persona_insight.upsert_active_meta_persona_insight(
                    cat["id"], period, gender, age,
                    g_ratio, a_ratio, gender_scale, age_scale, g_pv, a_pv, score,
                )
                rows_written += 1
    return rows_written
