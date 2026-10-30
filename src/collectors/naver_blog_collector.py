"""Naver 블로그 검색 API + 본문 스크래핑 + 반응 수(ADR-006) — 순수 API 호출만.

naver_news_collector.py와 구조는 같지만(검색 API 페이지네이션, 본문 스크래핑),
블로그 고유의 두 가지가 추가된다:
  1) platform 판정 — 검색 API가 blog.naver.com 외 티스토리 등도 반환하므로
     (2-2/2-1 실측, meta_blog.platform 참조) URL host로 플랫폼을 구분
  2) 반응 수 API — ADR-006에서 검증된 blog.like.naver.com (platform='naver'만 가능,
     브라우저 자동화 불필요. 댓글 수는 ADR-006에서 수집 불가로 결론났으므로 다루지 않음)
"""

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.common.retry import RetryableError, with_retry

SEARCH_API_URL = "https://openapi.naver.com/v1/search/blog.json"
REACTION_API_URL = "https://blog.like.naver.com/v1/search/contents"

_B_TAG_RE = re.compile(r"</?b>")
_NAVER_BLOG_PATH_RE = re.compile(r"blog\.naver\.com/([^/?]+)/(\d+)")

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_NAVER_CONTENT_SELECTORS = [
    "div.se-main-container",  # SmartEditor ONE (신형 에디터)
    "#postViewArea",          # 구형 에디터
    "#post-area",
]


def _strip_b_tags(text: str) -> str:
    import html
    return html.unescape(_B_TAG_RE.sub("", text))


def detect_platform(post_url: str) -> str:
    host = urlparse(post_url).netloc.lower()
    if "blog.naver.com" in host:
        return "naver"
    if "tistory.com" in host:
        return "tistory"
    if "brunch.co.kr" in host:
        return "brunch"
    if "wordpress.com" in host or "wordpress" in host:
        return "wordpress"
    if "blogspot.com" in host or "blogger.com" in host:
        return "blogger"
    return "other"


def parse_naver_blog_ids(post_url: str) -> Tuple[Optional[str], Optional[str]]:
    m = _NAVER_BLOG_PATH_RE.search(post_url)
    if m:
        return m.group(1), m.group(2)
    return None, None


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


def normalize_post(item: Dict[str, Any], search_keyword: str) -> Dict[str, Any]:
    post_url = item["link"]
    platform = detect_platform(post_url)
    blog_id, log_no = parse_naver_blog_ids(post_url) if platform == "naver" else (None, None)

    published_at = None
    postdate = item.get("postdate")
    if postdate and len(postdate) == 8:
        try:
            published_at = datetime.strptime(postdate, "%Y%m%d")
        except ValueError:
            pass

    return {
        "post_url": post_url,
        "title": _strip_b_tags(item["title"]),
        "description": _strip_b_tags(item.get("description", "")),
        "blogger_name": item.get("bloggername"),
        "blogger_link": item.get("bloggerlink"),
        "platform": platform,
        "blog_id": blog_id,
        "log_no": log_no,
        "published_at": published_at,
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


def fetch_post_content(post_url: str, platform: str, blog_id: Optional[str], log_no: Optional[str]) -> Optional[str]:
    """본문 스크래핑. naver는 PostView.naver로 접근(iframe 안 콘텐츠, 실제 GET으로 접근 가능)."""
    fetch_url = post_url
    if platform == "naver" and blog_id and log_no:
        fetch_url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"

    try:
        resp = requests.get(fetch_url, headers=_SCRAPE_HEADERS, timeout=10)
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


def fetch_reaction_stats(blog_id: str, log_no: str) -> Optional[Dict[str, Any]]:
    """ADR-006 검증된 방식 — platform='naver'만 가능. 브라우저 자동화 불필요."""
    headers = {**_SCRAPE_HEADERS, "Referer": f"https://blog.naver.com/{blog_id}/{log_no}"}
    q = f"BLOG[{blog_id}_{log_no}]"

    def _execute():
        resp = requests.get(REACTION_API_URL, headers=headers, params={"q": q}, timeout=10)
        if resp.status_code >= 500:
            raise RetryableError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            return None
        return resp.json()

    data = with_retry(_execute)
    if not data or not data.get("contents"):
        return None
    reactions = data["contents"][0].get("reactions", [])
    breakdown = {r["reactionType"]: r["count"] for r in reactions}
    return {"reaction_count": sum(breakdown.values()), "reaction_breakdown": breakdown}


def check_post_still_exists(post_url: str) -> Optional[bool]:
    """뉴스와 동일 원칙(04_Collection_Pipeline_Operations.md §6.1) — 검색 결과 부재만으로
    삭제 판정하지 않고 직접 재확인. True=존재, False=확실히 사라짐, None=판단 보류."""
    try:
        resp = requests.head(post_url, headers=_SCRAPE_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code in (404, 410):
            return False
        if resp.status_code == 200:
            return True
        return None
    except requests.RequestException:
        return None
