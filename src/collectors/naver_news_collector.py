"""Naver 뉴스 검색 API + 본문 스크래핑 + 댓글 수(ADR-005) — 순수 API 호출만.

레거시(3amd/naver_news.py)의 search_news/fetch_article_content를 포팅했다.
자격증명 하드코딩·인터랙티브 input() 등은 제거하고, 파라미터로 받는 형태로 정리.
댓글 수는 ADR-005에서 검증된 비공식 cbox5 API 패턴을 그대로 사용한다 —
is_naver_hosted=TRUE(news.naver.com/article/{oid}/{aid} 형식)인 기사만 가능.
"""

import html
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.common.retry import RetryableError, with_retry

SEARCH_API_URL = "https://openapi.naver.com/v1/search/news.json"
COMMENT_API_URL = "https://apis.naver.com/commentBox/cbox5/web_naver_list_jsonp.json"

_NAVER_HOSTED_RE = re.compile(r"news\.naver\.com/(?:mnews/)?article/(\d+)/(\d+)")
_B_TAG_RE = re.compile(r"</?b>")
_JSONP_RE = re.compile(r"^_callback\((.*)\);?$", re.DOTALL)

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_NAVER_CONTENT_SELECTORS = [
    "#newsct_article", "#articeBody", "#articleBodyContents",
    "div.newsct_article", "div._article_body",
]


def _strip_b_tags(text: str) -> str:
    return html.unescape(_B_TAG_RE.sub("", text))


def _search_page(client_id: str, client_secret: str, query: str, display: int, start: int, sort: str) -> Optional[dict]:
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": query, "display": display, "start": start, "sort": sort}

    def _execute():
        resp = requests.get(SEARCH_API_URL, headers=headers, params=params, timeout=15)
        if resp.status_code >= 500:
            raise RetryableError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            return None
        return resp.json()

    return with_retry(_execute)


def search_all(
    client_id: str, client_secret: str, query: str,
    max_pages: int = 3, display: int = 100, sort: str = "date",
) -> List[dict]:
    """검색어 1개로 최대 max_pages*display건(기본 300건) 수집 — API 제약상 start<=1000."""
    items: List[dict] = []
    for page in range(max_pages):
        start = page * display + 1
        if start > 1000:
            break
        data = _search_page(client_id, client_secret, query, display, start, sort)
        if not data or not data.get("items"):
            break
        items.extend(data["items"])
        if len(data["items"]) < display:
            break
        time.sleep(0.2)
    return items


def parse_naver_hosted(naver_url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    m = _NAVER_HOSTED_RE.search(naver_url)
    if m:
        return True, m.group(1), m.group(2)
    return False, None, None


def normalize_article(item: Dict[str, Any], search_keyword: str) -> Dict[str, Any]:
    is_hosted, oid, aid = parse_naver_hosted(item["link"])
    published_at = None
    try:
        published_at = parsedate_to_datetime(item["pubDate"])
    except (KeyError, TypeError, ValueError):
        pass

    return {
        "article_url": item["originallink"] or item["link"],
        "title": _strip_b_tags(item["title"]),
        "description": _strip_b_tags(item.get("description", "")),
        "naver_url": item["link"],
        "published_at": published_at,
        "is_naver_hosted": is_hosted,
        "naver_oid": oid,
        "naver_aid": aid,
        "publisher": urlparse(item["originallink"]).netloc or None,
        "search_keyword": search_keyword,
    }


# 본문이 아닌 영역 — 네이버 자체 페이지가 아닌 외부 매체는 전용 셀렉터가 걸리지
# 않아 <article>이나 <p> 폴백으로 떨어지고, 그때 내비·푸터·댓글 위젯이 본문에
# 딸려 들어온다. 2026-10-30 실측: 뉴스 본문 1,689건 중 300건(17.8%)에
# 발행인 정보·댓글 위젯 문구가 섞여 있었다.
#
# 이 텍스트는 모든 기사에 똑같이 들어가므로, 청크 최대 유사도 집계에서
# 질의와 무관하게 중간 점수를 내 무관한 기사를 상위로 올린다.
_NOISE_TAGS = ("script", "style", "nav", "footer", "aside", "header", "form", "iframe")
_NOISE_ATTR = re.compile(
    r"footer|comment|reply|banner|advert|_ad\b|sns|share|related|recommend|"
    r"copyright|subscribe|newsletter|breadcrumb|gnb|lnb|widget",
    re.IGNORECASE,
)


def _strip_non_content(soup):
    """본문 추출 전에 내비·푸터·댓글 영역을 DOM에서 제거한다."""
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    for tag in soup.find_all(attrs={"class": _NOISE_ATTR}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": _NOISE_ATTR}):
        tag.decompose()
    return soup


def fetch_article_content(url: str) -> Optional[str]:
    """기사 본문 스크래핑. 실패 시 None(has_content=FALSE로 처리)."""
    try:
        resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")
        _strip_non_content(soup)

        for selector in _NAVER_CONTENT_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                return tag.get_text(separator="\n", strip=True)

        article_tag = soup.find("article")
        if article_tag:
            return article_tag.get_text(separator="\n", strip=True)

        paragraphs = soup.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
        return text or None
    except Exception:
        return None


def check_article_still_exists(url: str) -> Optional[bool]:
    """True=존재, False=확실히 사라짐(404/410), None=판단 보류(네트워크 오류·애매한 상태코드).

    뉴스 검색 결과는 sort=date 슬라이딩 윈도우라 "이번 검색에 안 잡힘"이 "삭제됨"을
    의미하지 않는다(키워드가 활발하면 몇 분 만에도 상위 N건 밖으로 밀려날 수 있음).
    그래서 검색 결과 부재만으로 is_removed 처리하지 않고, 후보에 대해 URL을 직접
    재확인한다 — 명확히 404/410일 때만 삭제로 판정, 그 외(200/타임아웃/기타 오류)는
    보류해 오탐(false positive)을 피한다.
    """
    try:
        resp = requests.head(url, headers=_SCRAPE_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code in (404, 410):
            return False
        if resp.status_code == 200:
            return True
        return None
    except requests.RequestException:
        return None


def fetch_comment_stats(oid: str, aid: str) -> Optional[Dict[str, int]]:
    """ADR-005 검증된 비공식 API — is_naver_hosted 기사만 호출 가능."""
    url = (
        f"{COMMENT_API_URL}?ticket=news&templateId=default&pool=cbox5&lang=ko"
        f"&objectId=news{oid}%2C{aid}&pageSize=1&listType=OBJECT"
    )
    headers = {**_SCRAPE_HEADERS, "Referer": f"https://n.news.naver.com/mnews/article/{oid}/{aid}"}

    def _execute():
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code >= 500:
            raise RetryableError(f"HTTP {resp.status_code}")
        return resp.text

    text = with_retry(_execute)
    m = _JSONP_RE.match(text.strip())
    if not m:
        return None
    import json

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not data.get("success"):
        return None
    count = data.get("result", {}).get("count", {})
    return {
        "comment_count": count.get("comment"),
        "expose_count": count.get("exposeCount"),
        "reply_count": count.get("reply"),
    }
