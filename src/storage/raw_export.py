"""아이템 단위 raw 파일 쓰기 — architecture/05_Object_Storage_Export.md §2, §4.5 확정 스키마.

호출 시점(§5 확정): video/news/blog는 아이템이 신규 삽입되는 그 자리에서(콘텐츠가 이미
메모리에 있으므로), shopping/persona는 run() 끝에서 전체 데이터를 한 번에.
"""

import csv
import io
from typing import Any, Dict, List

from src.storage import s3_client


def write_video_transcript(
    dataset_id: str, video_id: str, segments: List[Dict[str, Any]], full_text: str, language: str
) -> str:
    """raw/video/{dataset_id}/{video_id}.json (§4.5 세그먼트 JSON 스키마).

    language는 Whisper가 감지한 실제 언어(youtube_transcript_collector.transcribe 참조) —
    이 콜렉터가 특정 언어 채널 전용이 아니라서 고정값을 쓰지 않는다.
    """
    key = f"raw/video/{s3_client.storage_key(dataset_id)}/{video_id}.json"
    s3_client.upload_json(
        key,
        {
            "video_id": video_id,
            "language": language,
            "segments": segments,
            "full_text": full_text,
        },
    )
    return key


def write_article_content(dataset_id: str, source_type: str, item_id: int, text: str) -> str:
    """raw/{source_type}/{dataset_id}/{item_id}.txt — news/blog 공용, item_id는 meta_* PK."""
    key = f"raw/{source_type}/{s3_client.storage_key(dataset_id)}/{item_id}.txt"
    s3_client.upload_text(key, text)
    return key


def write_declarative_csv(dataset_id: str, source_type: str, rows: List[Dict[str, Any]]) -> str:
    """raw/{source_type}/{dataset_id}/{dataset_id}.csv — 매 호출마다 전체 덮어쓰기.

    rows가 빈 리스트여도(카테고리는 있지만 아직 시계열이 없는 경우 등) 헤더만 있는
    빈 CSV를 씀 — 호출부에서 별도 분기 불필요.
    """
    key = f"raw/{source_type}/{s3_client.storage_key(dataset_id)}/{s3_client.storage_key(dataset_id)}.csv"
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    s3_client.upload_text(key, buf.getvalue())
    return key
