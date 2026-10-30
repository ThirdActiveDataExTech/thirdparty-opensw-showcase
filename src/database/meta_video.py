"""meta_video / active_meta_video 읽기·쓰기 헬퍼."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.database.db import get_conn


def get_existing_video_ids(dataset_id: str) -> Dict[str, int]:
    """이 dataset_id에 이미 등록된 {video_id: meta_id}."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT video_id, id FROM meta_video WHERE dataset_id = %s",
            (dataset_id,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def insert_meta_video(dataset_id: str, video: Dict[str, Any]) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO meta_video (
                dataset_id, video_id, title, description, published_at,
                channel_id, channel_title, tags, category_id, topic_categories,
                duration, duration_seconds, definition,
                default_language, default_audio_language, has_caption,
                thumbnail_url, initial_view_count, initial_like_count, initial_comment_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                dataset_id, video["video_id"], video["title"], video["description"],
                video["published_at"], video["channel_id"], video["channel_title"],
                json.dumps(video["tags"]), video["category_id"],
                json.dumps(video["topic_categories"]), video["duration"],
                video["duration_seconds"], video["definition"],
                video["default_language"], video["default_audio_language"],
                video["has_caption"], video["thumbnail_url"],
                video["view_count"], video["like_count"], video["comment_count"],
            ),
        )
        meta_id = cur.fetchone()[0]
        conn.commit()
        return meta_id
    finally:
        conn.close()


def get_latest_active_meta(meta_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT view_count, like_count, comment_count
            FROM active_meta_video
            WHERE meta_id = %s
            ORDER BY collected_at DESC
            LIMIT 1
            """,
            (meta_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"view_count": row[0], "like_count": row[1], "comment_count": row[2]}
    finally:
        conn.close()


def insert_active_meta_video(
    meta_id: int,
    stats: Dict[str, Any],
    delta_views: Optional[int] = None,
    delta_likes: Optional[int] = None,
    delta_comments: Optional[int] = None,
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO active_meta_video
                (meta_id, view_count, like_count, comment_count,
                 delta_views, delta_likes, delta_comments)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                meta_id, stats["view_count"], stats["like_count"], stats["comment_count"],
                delta_views, delta_likes, delta_comments,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_removed(meta_id: int, removed_at: datetime) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE meta_video SET is_removed = TRUE, removed_at = %s WHERE id = %s",
            (removed_at, meta_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_transcribed(meta_id: int, transcribed_at: datetime) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE meta_video SET has_transcript = TRUE, transcribed_at = %s WHERE id = %s",
            (transcribed_at, meta_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_untranscribed(dataset_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """트랜스크립트가 없는(has_transcript=FALSE) 삭제되지 않은 영상 — 백필 스크립트용."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        if dataset_id is not None:
            cur.execute(
                """
                SELECT id, dataset_id, video_id FROM meta_video
                WHERE has_transcript = FALSE AND is_removed = FALSE AND dataset_id = %s
                ORDER BY id LIMIT %s
                """,
                (dataset_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, dataset_id, video_id FROM meta_video
                WHERE has_transcript = FALSE AND is_removed = FALSE
                ORDER BY id LIMIT %s
                """,
                (limit,),
            )
        return [{"id": r[0], "dataset_id": r[1], "video_id": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()
