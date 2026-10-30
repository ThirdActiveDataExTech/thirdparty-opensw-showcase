"""Naver DataLab Persona (성별 API + 연령 API, 독립 가정) — 순수 API 호출만.

레거시(3amd/naver_persona.py)의 fetch_api/parse_persona_response를 포팅했다.
shopping_insight와 달리 anchor/배칭이 없다 — 카테고리 1개당 API 2개(성별/연령)를
각각 독립 호출한다. category 파라미터도 리스트가 아니라 ID 문자열 하나.

레거시의 time.sleep(delay) rate limiting을 처음 포팅할 때 빠뜨렸다(2026-07-28
발견·수정) — naver_shopping_collector.py와 동일하게 호출 성공 직후 쉰다.
"""

import time
from typing import Dict, Optional

import requests

from src.common.retry import RetryableError, with_retry

GENDER_API_URL = "https://openapi.naver.com/v1/datalab/shopping/category/gender"
AGE_API_URL = "https://openapi.naver.com/v1/datalab/shopping/category/age"
REQUEST_DELAY_SECONDS = 1.0


def fetch_ratios(
    url: str,
    client_id: str,
    client_secret: str,
    start_date: str,
    end_date: str,
    time_unit: str,
    category_id: str,
) -> Optional[dict]:
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "category": category_id,  # 성별/연령 API는 ID 문자열 단독 사용 (배열 아님)
    }

    def _execute():
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code >= 500:
            raise RetryableError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            return None
        return resp.json()

    result = with_retry(_execute)
    time.sleep(REQUEST_DELAY_SECONDS)
    return result


def parse_persona_response(data: dict) -> Dict[str, Dict[str, float]]:
    """API 응답 → {period: {group: ratio}}.

    gender API: group = 'm'/'f'.  age API: group = '10'..'60'.
    """
    result: Dict[str, Dict[str, float]] = {}
    for r in data.get("results", []):
        for item in r.get("data", []):
            period = item["period"]
            group = str(item["group"])
            result.setdefault(period, {})[group] = item["ratio"]
    return result
