"""Naver 쇼핑인사이트 선언형 파이프라인 — architecture/04_Collection_Pipeline_Operations.md
§6.2 그대로 구현.

shopping_insight/persona_insight는 신규/기존 분기도 삭제 감지도 필요 없다 —
meta_shopping_insight의 카테고리 목록은 등록 시점에 사용자가 이미 확정한 것이라
Collector가 목록 자체를 바꾸지 않는다.

날짜 범위는 "어제 하루만"이 아니라 **DB에 저장된 마지막 날짜 - OVERLAP_DAYS부터
어제까지**를 매번 다시 가져온다(2026-07-28 수정, 최초엔 하루만 가져왔었음). 이렇게
겹치는 구간을 두는 이유 두 가지:
  1) inter_scale(수집 구간 간 보정)이 실제로 작동하려면 이번 수집 결과와 DB의
     기존 값이 "같은 날짜"를 가리켜야 한다. 하루씩만 가져오면 겹치는 날짜가 절대
     없어서 inter_scale이 항상 1.0으로 죽어있었다 — pseudo_volume의 핵심 목적
     (여러 수집 구간을 하나의 연속 시계열로 잇기)이 실질적으로 무의미했던 버그.
  2) Airflow가 며칠 멈췄다 재개되는 경우, 그 사이 결측 구간을 OVERLAP_DAYS 범위
     안에서는 자동으로 보충한다(그보다 오래된 결측은 못 채움).
UPSERT라 겹치는 날짜를 다시 써도 중복 행은 안 생기고, 최신 scale_factor로
재계산돼서 덮어써진다.

**최초 수집 시 소급 수집**(2026-07-28 추가): `dcat_dataset.temporal_start`에
값이 있으면(등록 시 프론트엔드/관리자가 지정) 그 날짜부터 소급 수집한다 — 레거시
`--auto`의 "데이터 없으면 1년 전부터" 2단계 로직과 같은 목적이지만, 날짜 범위
하나로 한 번에 호출한다(레거시는 왜 2단계로 나눴는지 특별한 이유가 없어 보여서
단순화 — 어차피 한 번의 API 호출 응답 안에서는 M값이 하나로 통일되니 오히려
더 일관됨). 지정 안 하면 기존과 동일하게 OVERLAP_DAYS만큼만. 첫 수집 성공 후
`dcat_dataset.temporal_start`를 실제로 수집된 가장 이른 날짜로 갱신한다(그
이후엔 건드리지 않음 — 나중 수집은 항상 앞으로만 진행하니 시작일이 당겨질
일이 없음).

anchor 카테고리는 모든 배치 호출에 포함시켜 호출당 최대 3카테고리 제약을
맞춘다(비-anchor 2개씩 묶음). intra_scale(배치 간)·inter_scale(수집 구간 간)
보정은 naver_datalab_scale.py 참조.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.collectors import naver_datalab_scale, naver_shopping_collector
from src.database import category, dcat, meta_shopping_insight, theme
from src.database.db import get_conn
from src.embedding import sync as embedding_sync
from src.storage import jsonld_export

AGENT = "naver_shopping_collector"
logger = logging.getLogger(__name__)
GENDERS = ["m", "f"]
AGES = ["10", "20", "30", "40", "50", "60"]
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
            SELECT count(*) FROM active_meta_shopping_insight a
            JOIN meta_shopping_insight m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _chunk(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def _compute_fetch_range(dataset_id: str, dataset: Dict[str, Any]) -> Tuple[str, str]:
    """(start_date, end_date).

    최초 수집(last_period 없음)이면 dcat_dataset.temporal_start가 지정돼 있을 때
    그 날짜부터 소급 수집 — 없으면 기존과 동일하게 OVERLAP_DAYS만큼만.
    이미 수집 이력이 있으면 마지막 저장 날짜 - OVERLAP_DAYS부터.
    """
    end_date = date.today() - timedelta(days=1)  # 당일 데이터는 API에 아직 안 실릴 수 있음
    last_period = meta_shopping_insight.get_last_period(dataset_id)
    if last_period is None:
        desired_start = dataset.get("temporal_start")  # date 객체 또는 None
        start_date = desired_start if desired_start is not None else end_date - timedelta(days=OVERLAP_DAYS)
    else:
        start_date = min(date.fromisoformat(last_period) - timedelta(days=OVERLAP_DAYS), end_date)
    return start_date.isoformat(), end_date.isoformat()


def _current_temporal_start(dataset_id: str) -> Optional[str]:
    """실제로 지금까지 수집된 가장 이른 period. 데이터 없으면 None."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MIN(a.period) FROM active_meta_shopping_insight a
            JOIN meta_shopping_insight m ON m.id = a.meta_id
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

    categories = meta_shopping_insight.get_meta_shopping_insight_rows(dataset_id)
    anchor = next(c for c in categories if c["is_anchor"])
    non_anchor = [c for c in categories if not c["is_anchor"]]
    batches = _chunk(non_anchor, 2)

    start_date, end_date = _compute_fetch_range(dataset_id, dataset)
    started_at = datetime.now(timezone.utc)
    rows_written = 0

    try:
        for gender in GENDERS:
            for age in AGES:
                rows_written += _collect_one_combo(
                    dataset_id, anchor, batches, gender, age,
                    start_date, end_date, client_id, client_secret,
                )

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
            themes = theme.sync_theme(dataset_id, "shopping_insight")
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
            stat = embedding_sync.sync_for_dataset("shopping_insight", dataset_id)
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


def _collect_one_combo(
    dataset_id: str,
    anchor: Dict[str, Any],
    batches: List[List[Dict[str, Any]]],
    gender: str,
    age: str,
    start_date: str,
    end_date: str,
    client_id: str,
    client_secret: str,
) -> int:
    """(gender, age) 조합 1개에 대해 배치 전부 호출 → scale 보정 → 저장. 저장 행 수 반환."""
    anchor_pair = (anchor["category_id"], anchor["category_name"])

    # Step 1: 이 (gender, age)의 모든 배치 호출 — start_date~end_date 범위 전체(여러 날짜)
    batch_results: List[Tuple[int, List[Dict[str, Any]], Any]] = []
    for b_idx, batch in enumerate(batches):
        cats_in_call = [anchor_pair] + [(c["category_id"], c["category_name"]) for c in batch]
        data = naver_shopping_collector.fetch_insight(
            client_id, client_secret, start_date, end_date, "date",
            cats_in_call, gender, age,
        )
        parsed = naver_shopping_collector.parse_response(data) if data else None
        batch_results.append((b_idx, batch, parsed))

    # Step 2: 첫 유효 배치를 기준(ref) anchor로 사용, DB 기존값과 비교해 inter_scale 계산
    ref_anchor: Dict[str, float] = {}
    ref_batch_idx = -1
    for b_idx, _, parsed in batch_results:
        if parsed and parsed.get(anchor["category_name"]):
            ref_anchor = parsed[anchor["category_name"]]
            ref_batch_idx = b_idx
            break

    existing_anchor = meta_shopping_insight.get_existing_anchor_raw(
        anchor["id"], gender, age, list(ref_anchor.keys())
    )
    inter_scale = naver_datalab_scale.compute_inter_scale(existing_anchor, ref_anchor)

    # Step 3: 배치별 intra_scale 계산 후 저장
    rows_written = 0
    for b_idx, batch, parsed in batch_results:
        if not parsed:
            continue
        batch_anchor = parsed.get(anchor["category_name"], {})
        intra_scale = naver_datalab_scale.median_ratio(ref_anchor, batch_anchor) if batch_anchor else 1.0
        scale_factor = inter_scale * intra_scale

        if b_idx == ref_batch_idx:
            for period, raw in batch_anchor.items():
                meta_shopping_insight.upsert_active_meta_shopping_insight(
                    anchor["id"], period, gender, age,
                    raw_ratio=raw, anchor_raw_ratio=raw, normalized_ratio=100.0,
                    scale_factor=scale_factor, pseudo_volume=raw * scale_factor,
                    batch_index=b_idx,
                )
                rows_written += 1

        for cat in batch:
            cat_by_period = parsed.get(cat["category_name"], {})
            for period, raw in cat_by_period.items():
                anchor_raw = batch_anchor.get(period)
                normalized = raw / anchor_raw * 100.0 if anchor_raw else None
                meta_shopping_insight.upsert_active_meta_shopping_insight(
                    cat["id"], period, gender, age,
                    raw_ratio=raw, anchor_raw_ratio=anchor_raw, normalized_ratio=normalized,
                    scale_factor=scale_factor, pseudo_volume=raw * scale_factor,
                    batch_index=b_idx,
                )
                rows_written += 1

    return rows_written
