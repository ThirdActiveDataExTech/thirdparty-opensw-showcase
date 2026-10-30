"""meta_news / active_meta_news 읽기·쓰기 헬퍼."""

from datetime import datetime
from typing import Any, Dict, Optional

from src.database.db import get_conn


def get_existing_articles(dataset_id: str) -> Dict[str, Dict[str, Any]]:
    """{article_url: {id, published_at, is_naver_hosted, naver_oid, naver_aid, is_removed}}."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT article_url, id, published_at, is_naver_hosted, naver_oid, naver_aid, is_removed
            FROM meta_news WHERE dataset_id = %s
            """,
            (dataset_id,),
        )
        return {
            row[0]: {
                "id": row[1], "published_at": row[2],
                "is_naver_hosted": row[3], "naver_oid": row[4], "naver_aid": row[5],
                "is_removed": row[6],
            }
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def insert_meta_news(dataset_id: str, article: Dict[str, Any], content: Optional[str]) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO meta_news (
                dataset_id, article_url, title, description, content, has_content,
                publisher, naver_url, published_at,
                is_naver_hosted, naver_oid, naver_aid, search_keyword
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                dataset_id, article["article_url"], article["title"], article["description"],
                content, content is not None,
                article["publisher"], article["naver_url"], article["published_at"],
                article["is_naver_hosted"], article["naver_oid"], article["naver_aid"],
                article["search_keyword"],
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
            "UPDATE meta_news SET is_removed = TRUE, removed_at = %s WHERE id = %s",
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
            "UPDATE meta_news SET is_removed = FALSE, removed_at = NULL WHERE id = %s",
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
            SELECT comment_count FROM active_meta_news
            WHERE meta_id = %s ORDER BY collected_at DESC LIMIT 1
            """,
            (meta_id,),
        )
        row = cur.fetchone()
        return {"comment_count": row[0]} if row else None
    finally:
        conn.close()


def insert_active_meta_news(
    meta_id: int, comment_count, expose_count, reply_count, delta_comments=None
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO active_meta_news
                (meta_id, comment_count, expose_count, reply_count, delta_comments)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (meta_id, comment_count, expose_count, reply_count, delta_comments),
        )
        conn.commit()
    finally:
        conn.close()
