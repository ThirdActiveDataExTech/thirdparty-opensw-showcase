"""간단한 재시도+백오프 헬퍼.

레거시(3amd) 스크립트들은 재시도 로직이 전혀 없었다(고정 sleep만). 외부 의존성
(tenacity 등) 추가 없이 순수 Python으로 최소한의 재시도만 구현한다 — 일시적
네트워크 오류/5xx에 한해 재시도, 4xx(쿼터 초과 등 클라이언트 오류)는 재시도해도
소용없으므로 즉시 실패시킨다.
"""

import time

import requests
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryableError(Exception):
    """일시적 오류 — 재시도 대상."""


# 네트워크가 잠깐 흔들려서 나는 예외들. 재시도하면 대개 성공한다.
#
# 2026-10-29: blog.like.naver.com(반응 수 API) ReadTimeout이 재시도되지 않고
# 그대로 전파돼 **데이터셋 수집 전체가 실패**했다. RetryableError만 잡고 있어서
# requests의 타임아웃·연결오류는 "재시도 무의미"로 분류되고 있었는데, 이 둘은
# 전형적인 일시 오류다.
_RETRYABLE = (
    RetryableError,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> T:
    """fn()을 호출하고, RetryableError 발생 시에만 지수 백오프로 재시도한다.

    RetryableError가 아닌 예외는 즉시 전파한다(재시도 무의미한 오류로 간주).
    """
    last_error = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except _RETRYABLE as e:
            last_error = e
            if attempt < max_attempts - 1:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
    raise last_error
