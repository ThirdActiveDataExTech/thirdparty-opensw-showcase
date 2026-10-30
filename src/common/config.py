"""환경변수 로딩 — scripts/embed_*.py의 load_dotenv 패턴을 공유 모듈로 옮긴 것."""

import os
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수 {name}가 설정되지 않았습니다 (.env 확인)")
    return value


def mask_secrets(text: str) -> str:
    """로그·예외 메시지에 섞여 나온 자격증명을 가린다.

    googleapiclient는 API 키를 `?key=...` 쿼리 파라미터로 보내고, HttpError의
    문자열에는 요청 URI가 그대로 들어간다. 즉 쿼터 초과 같은 흔한 오류 하나로
    **터미널과 스크린샷에 실제 키가 찍힌다.** 로그 레벨과 무관하게 발생한다.

    데모 녹화·이슈 첨부처럼 화면이 외부로 나갈 때를 전제로, 키가 오류 경로로
    새는 것을 코드에서 막는다.
    """
    masked = text
    for value in _all_secret_values():
        if value and len(value) >= 8:
            masked = masked.replace(value, value[:4] + "***")
    return re.sub(r"([?&](?:key|api_key|access_token)=)[^&\s\"']+", r"\1***", masked)


def _all_secret_values() -> list:
    names = ("YOUTUBE_API_KEY", "YOUTUBE_API_KEY_BACKUP", "YOUTUBE_API_KEY_BACKUP2",
             "NAVER_CLIENT_SECRET", "NAVER_CLIENT_ID", "S3_SECRET_KEY",
             "S3_ACCESS_KEY", "DB_PASSWORD", "ENCRYPTION_KEY")
    return [v for v in (os.getenv(n) for n in names) if v]


def get_youtube_api_keys() -> list:
    """YouTube API 키 목록 [기본, 예비...] — 값이 있는 것만. 첫 키 소진 시 다음 키로 전환용.
    주의: YouTube 일일 할당량은 GCP '프로젝트' 단위다. 예비키가 별도 프로젝트일 때만
    실제로 할당량이 늘어난다(같은 프로젝트면 동일 쿼터 공유)."""
    names = ["YOUTUBE_API_KEY", "YOUTUBE_API_KEY_BACKUP", "YOUTUBE_API_KEY_BACKUP2"]
    return [k for k in (os.getenv(n) for n in names) if k]


# 접속 정보는 .env/Secret에서만 온다. 내부망 주소를 기본값으로 두면 저장소에
# 남고, .env 없이 돌렸을 때 조용히 엉뚱한 곳에 붙는다 — 없으면 바로 실패시킨다.
DB_HOST = require_env("DB_HOST")
DB_PORT = int(get_env("DB_PORT", "30433"))
DB_NAME = get_env("DB_NAME", "datagokr")
DB_USER = get_env("DB_USER")
DB_PASSWORD = get_env("DB_PASSWORD")

TRIGGERED_BY = get_env("TRIGGERED_BY", "manual")

S3_ENDPOINT = require_env("S3_ENDPOINT")
S3_ACCESS_KEY = get_env("S3_ACCESS_KEY")
S3_SECRET_KEY = get_env("S3_SECRET_KEY")
S3_BUCKET = get_env("S3_BUCKET", "metadata-ingestion")
S3_REGION = get_env("S3_REGION", "us-east-1")
