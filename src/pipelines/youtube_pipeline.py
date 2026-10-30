"""YouTube 발견형 파이프라인 — architecture/04_Collection_Pipeline_Operations.md §6.1 그대로 구현.

run(dataset_id, triggered_by)이 Airflow/CLI가 호출하는 유일한 진입점이다.
collectors(순수 API 호출)와 database(순수 DB IO) 모듈을 조합해 다음을 수행한다:
  1. 채널 전체 발견(subjects.channels) + 관리자가 직접 지정한 개별 영상
     (subjects.videos) 목록 조회 — 채널 큐레이션과 개별 영상 큐레이션을 한
     데이터셋 안에 섞을 수 있다(2026-07-28 확장). 개별 지정 영상은 채널
     페이지네이션을 안 거치고 video_id로 직접 조회하므로 Shorts 필터가 없다
     (명시적으로 고른 걸 존중 — youtube_collector.fetch_specific_videos 참조).
  2. DB에 이미 있는 영상과 비교해 신규/기존 분기
  3. 기존 영상은 시계열 스냅샷만 추가(delta 계산), 신규 영상은 meta+최초 스냅샷 INSERT
  4. 원격(채널 전체 목록이든 개별 조회든)에서 더 이상 안 보이는 영상은 is_removed=TRUE
     (재등장 시 자동 해제) — 개별 지정 영상도 video_id 직접 조회라 "조회 실패=삭제"가
     news/blog의 슬라이딩 윈도우 검색과 달리 안전하게 성립한다(직접 조회는 있으면
     있고 없으면 없고, 순위 밖으로 밀려나는 개념 자체가 없음)
  5. dcat_provenance INSERT + data_registry UPDATE (실패 시 재시도 스케줄 앞당김)
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.common import config
from src.collectors import youtube_collector, youtube_transcript_collector
from src.database import category, dcat, theme
from src.database import meta_video
from src.database.db import get_conn
from src.embedding import sync as embedding_sync
from src.storage import jsonld_export, raw_export

AGENT = "youtube_collector"
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
        cur.execute("SELECT count(*) FROM meta_video WHERE dataset_id = %s", (dataset_id,))
        return cur.fetchone()[0]
    finally:
        conn.close()


def _current_row_count(dataset_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*) FROM active_meta_video a
            JOIN meta_video m ON m.id = a.meta_id
            WHERE m.dataset_id = %s
            """,
            (dataset_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _clear_removed_flag(meta_id: int) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE meta_video SET is_removed = FALSE, removed_at = NULL WHERE id = %s",
            (meta_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _compute_delta(prev: Dict[str, Any], video: Dict[str, Any], key: str) -> Any:
    prev_val, new_val = prev.get(key), video.get(key)
    if prev_val is None or new_val is None:
        return None
    return new_val - prev_val


def _fetch_remote_videos(service, channel_ids: list, video_ids: list) -> list:
    """channels+videos를 합쳐서 중복 제거된 영상 목록 반환.

    같은 video_id가 채널 발견과 개별 지정 양쪽에 다 걸릴 수 있어(예: 이미
    추적 중인 채널의 영상을 실수로 개별 지정에도 넣은 경우) news/blog와 같은
    이유로 중복 제거가 필요 — 안 하면 두 번째 발생 시 중복 INSERT 시도로 에러난다.
    """
    seen = set()
    videos = []
    for channel_id in channel_ids:
        for video in youtube_collector.fetch_channel_videos(service, channel_id):
            if video["video_id"] not in seen:
                seen.add(video["video_id"])
                videos.append(video)
    if video_ids:
        for video in youtube_collector.fetch_specific_videos(service, video_ids):
            if video["video_id"] not in seen:
                seen.add(video["video_id"])
                videos.append(video)
    return videos


# ── 자막(STT) 처리 예산 ──────────────────────────────────────────────────
#
# 자막은 B1(키워드 추출)·A2(AI 메타데이터)의 입력이라 **수집 파이프라인 안에서
# 자동으로 만들어져야 한다.** 다만 영상마다 전부 돌리면 수집이 끝나지 않는다 —
# 2026-10-29 실측으로 영상 1건당 약 1.4분, 채널 4개(약 1,500건)에 35시간이 나왔다.
# 등록 화면이 "수집 중"에서 영영 안 빠진다.
#
# 그래서 **켜고 끄는 대신 한 회차에 쓸 시간을 제한한다.** 수집 본체가 끝난 뒤
# 남은 예산만큼 자막을 만들고, 못 한 분량은 다음 수집 회차가 이어서 처리한다
# (has_transcript=FALSE가 대상이라 자연히 이어진다).
#
#   수집 주기 P7D, 예산 10분 → 회차당 약 7건 → 72건 채널이면 약 10주
#   백로그를 빨리 줄이려면 scripts/backfill_youtube_transcripts.py를 따로 돌린다
#
# 0으로 두면 자막 단계를 건너뛴다(개발·점검용).
TRANSCRIPT_BUDGET_SEC = int(config.get_env("YOUTUBE_TRANSCRIPT_BUDGET_SEC", "600"))



def _normalize_subjects(subjects: Any) -> Tuple[List[str], List[str]]:
    """subjects를 (채널 ID 목록, 개별 영상 ID 목록)으로 정규화한다.

    두 형태가 공존한다.

      배열형  ["UCxxxx", ...]                        2026-07-28 이전 등록분
      객체형  {"channels": [...], "videos": [...]}   2026-07-28 확장 이후

    확장할 때 객체형만 처리하도록 바꿔서 **배열형 데이터셋 10건이 수집 불가
    상태였다**(2026-10-28 발견 — TypeError: the JSON object must be str...).
    배열형은 "채널만 있고 개별 영상은 없다"는 뜻이므로 videos를 빈 목록으로 둔다.

    psycopg2는 jsonb를 파이썬 객체(list/dict)로 돌려주지만, 호출부가 문자열을
    넘기는 경우도 받아 준다.
    """
    if isinstance(subjects, (str, bytes)):
        subjects = json.loads(subjects)
    if isinstance(subjects, dict):
        return list(subjects.get("channels") or []), list(subjects.get("videos") or [])
    if isinstance(subjects, list):
        return list(subjects), []
    raise ValueError(
        f"subjects 형식을 알 수 없습니다: {type(subjects).__name__} — "
        f"배열(채널 ID 목록) 또는 {{'channels': [...], 'videos': [...]}} 이어야 합니다"
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
            "SELECT MIN(published_at)::date FROM meta_video WHERE dataset_id = %s",
            (dataset_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _transcribe_within_budget(dataset_id: str) -> int:
    """자막이 없는 영상을 예산(초) 안에서 처리한다. 반환: 생성한 건수.

    한 건이 실패해도 다음 건으로 넘어간다 — 특정 영상의 오디오를 못 받는 경우가
    흔하고(비공개 전환, 지역 제한), 그것 때문에 나머지를 포기할 이유가 없다.
    """
    if TRANSCRIPT_BUDGET_SEC <= 0:
        return 0
    deadline = time.monotonic() + TRANSCRIPT_BUDGET_SEC
    done = 0
    # 예산을 넘지 않는 선에서 넉넉히 가져온다 — 실제 중단은 deadline이 결정한다
    for row in meta_video.get_untranscribed(dataset_id=dataset_id, limit=500):
        if time.monotonic() >= deadline:
            break
        try:
            transcript = youtube_transcript_collector.fetch_transcript(row["video_id"])
            if transcript is None:
                continue
            segments, full_text, language = transcript
            raw_export.write_video_transcript(
                dataset_id, row["video_id"], segments, full_text, language
            )
            meta_video.mark_transcribed(
                row["id"], transcribed_at=datetime.now(timezone.utc))
            done += 1
        except Exception as e:
            logger.warning(
                "자막 처리 실패 (video_id=%s): %s — 다음 영상으로 진행",
                row["video_id"], e,
            )
    return done


def run(dataset_id: str, triggered_by: str) -> None:
    dataset = dcat.fetch_dcat_dataset(dataset_id)
    was_pending = _get_registry_status(dataset_id) == "pending"
    api_key = dcat.get_api_key(dataset_id, "youtube_api_key")
    channel_ids, video_ids = _normalize_subjects(dataset["subjects"])
    started_at = datetime.now(timezone.utc)

    try:
        service = youtube_collector.build_service(api_key)
        existing = meta_video.get_existing_video_ids(dataset_id)  # {video_id: meta_id}, is_removed 무관 전부
        remote_ids = set()
        new_count, updated_count, removed_count = 0, 0, 0

        for video in _fetch_remote_videos(service, channel_ids, video_ids):
            remote_ids.add(video["video_id"])
            if video["video_id"] not in existing:
                meta_id = meta_video.insert_meta_video(dataset_id, video)
                meta_video.insert_active_meta_video(meta_id, video)
                new_count += 1
            else:
                meta_id = existing[video["video_id"]]
                prev = meta_video.get_latest_active_meta(meta_id)
                if prev is not None:
                    meta_video.insert_active_meta_video(
                        meta_id, video,
                        delta_views=_compute_delta(prev, video, "view_count"),
                        delta_likes=_compute_delta(prev, video, "like_count"),
                        delta_comments=_compute_delta(prev, video, "comment_count"),
                    )
                else:
                    meta_video.insert_active_meta_video(meta_id, video)
                _clear_removed_flag(meta_id)  # 재등장 시 removed 해제
                updated_count += 1

        for video_id, meta_id in existing.items():
            if video_id not in remote_ids:
                meta_video.mark_removed(meta_id, removed_at=datetime.now(timezone.utc))
                removed_count += 1

        ended_at = datetime.now(timezone.utc)

        dcat.insert_dcat_provenance(
            dataset_id, activity_type="initial" if was_pending else "update",
            agent=AGENT, triggered_by=triggered_by,
            started_at=started_at, ended_at=ended_at, status="success",
            rows_affected=new_count + updated_count,
            params={"channels": channel_ids, "videos": video_ids},
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

        # 자막(STT) — 예산 안에서만. 남은 분량은 다음 회차가 이어서 한다.
        try:
            n = _transcribe_within_budget(dataset_id)
            if n:
                logger.info("자막 %d건 생성", n)
        except Exception as e:
            logger.warning(f"자막 처리 실패, 수집 자체는 성공 처리: {e}")

        # theme(원천 분류 원문) 집계 — 수집 결과에서 다시 계산한다.
        # video는 YouTube 카테고리+위키 주제, 선언형은 쇼핑 카테고리 대분류.
        # news/blog는 원천이 분류를 주지 않아 이 단계가 없다(src/database/theme.py).
        try:
            themes = theme.sync_theme(dataset_id, "video")
            if themes:
                logger.info("theme %d종 반영: %s", len(themes), ", ".join(themes[:4]))
        except Exception as e:
            logger.warning(f"theme 집계 실패, 수집 자체는 성공 처리: {e}")

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
            stat = embedding_sync.sync_for_dataset("video", dataset_id)
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
