"""meta_blog / active_meta_blog 읽기·쓰기 헬퍼."""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from src.database.db import get_conn


def get_existing_posts(dataset_id: str) -> Dict[str, Dict[str, Any]]:
    """{post_url: {id, platform, blog_id, log_no, is_removed}}."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT post_url, id, platform, blog_id, log_no, is_removed
            FROM meta_blog WHERE dataset_id = %s
            """,
            (dataset_id,),
        )
        return {
            row[0]: {
                "id": row[1], "platform": row[2], "blog_id": row[3],
                "log_no": row[4], "is_removed": row[5],
            }
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def insert_meta_blog(dataset_id: str, post: Dict[str, Any], content: Optional[str]) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO meta_blog (
                dataset_id, post_url, title, description, content, has_content,
                blogger_name, blogger_link, platform, blog_id, log_no,
                published_at, search_keyword
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                dataset_id, post["post_url"], post["title"], post["description"],
                content, content is not None,
                post["blogger_name"], post["blogger_link"], post["platform"],
                post["blog_id"], post["log_no"], post["published_at"], post["search_keyword"],
            ),
        )
        meta_id = cur.fetchone()[0]
        conn.commit()
        return meta_id
    finally:
        conn.close()


def mark_removed(meta_id: int, removed_at: datetime) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE meta_blog SET is_removed = TRUE, removed_at = %s WHERE id = %s",
            (removed_at, meta_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_removed_flag(meta_id: int) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE meta_blog SET is_removed = FALSE, removed_at = NULL WHERE id = %s",
            (meta_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_active_meta(meta_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT reaction_count FROM active_meta_blog
            WHERE meta_id = %s ORDER BY collected_at DESC LIMIT 1
            """,
            (meta_id,),
        )
        row = cur.fetchone()
        return {"reaction_count": row[0]} if row else None
    finally:
        conn.close()


def insert_active_meta_blog(
    meta_id: int, reaction_count: int, reaction_breakdown: dict, delta_reactions: Optional[int] = None
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO active_meta_blog (meta_id, reaction_count, reaction_breakdown, delta_reactions)
            VALUES (%s, %s, %s, %s)
            """,
            (meta_id, reaction_count, json.dumps(reaction_breakdown), delta_reactions),
        )
        conn.commit()
    finally:
        conn.close()
