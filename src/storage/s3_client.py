"""SeaweedFS(S3 호환) 클라이언트 — infrastructure/04_ObjectStorage.md의 접속 정보 사용.

architecture/05_Object_Storage_Export.md §5 결정에 따라, 이 모듈의 업로드 함수들은
실패 시 예외를 그대로 올린다(삼키지 않음) — 예외를 삼켜서 "수집 자체는 성공 처리"하는
판단은 호출부(파이프라인)의 책임이지 이 모듈의 책임이 아니다.
"""

import json
from typing import Any, Dict

import boto3
from botocore.config import Config

from src.common import config

_client = None


def get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=config.S3_ENDPOINT,
            aws_access_key_id=config.S3_ACCESS_KEY,
            aws_secret_access_key=config.S3_SECRET_KEY,
            region_name=config.S3_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


def upload_text(key: str, text: str) -> None:
    get_s3_client().put_object(
        Bucket=config.S3_BUCKET, Key=key, Body=text.encode("utf-8"), ContentType="text/plain; charset=utf-8"
    )


def upload_json(key: str, obj: Dict[str, Any]) -> None:
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    get_s3_client().put_object(
        Bucket=config.S3_BUCKET, Key=key, Body=body.encode("utf-8"), ContentType="application/json; charset=utf-8"
    )


def storage_key(dataset_id: str) -> str:
    """dataset_id를 오브젝트 키에 쓸 수 있는 경로 조각으로 바꾼다.

    2026-10-28 dataset_id가 slug에서 URN(`urn:naver:news_ai`)으로 바뀌었다.
    콜론은 S3 키에 쓸 수는 있지만 URL 인코딩·CLI 인용·일부 도구에서 걸리므로
    경로에는 넣지 않는다. `urn:` 접두를 떼고 나머지 콜론을 `_`로 바꾼다.

        urn:naver:news_ai          → naver_news_ai
        urn:youtube:samsung_official → youtube_samsung_official

    **이 변환은 전환 전 slug와 같은 값을 돌려준다** — 그래서 URN 전환 후에도
    기존 S3 경로가 그대로 유지된다(실측: 객체가 있는 경로 6개 전부 보존).
    S3에는 rename이 없어 경로 이전은 복사 후 삭제가 필요한데, 경로가 식별자와
    일치해야 할 이유가 없어 그 비용을 치르지 않기로 했다.
    (docs/database/dataset_id_urn_migration.md §2.2)

    예외는 `user_hbm_video_collection` → `youtube_hbm_video_collection` 하나뿐이고,
    이 데이터셋에는 S3 객체가 없다.
    """
    if dataset_id.startswith("urn:"):
        return dataset_id[4:].replace(":", "_")
    return dataset_id
