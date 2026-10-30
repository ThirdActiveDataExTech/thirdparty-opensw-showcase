"""YouTube 영상 카테고리 ID → 이름.

YouTube Data API `videoCategories.list`가 돌려주는 고정 목록이다. 지역(`regionCode`)에
따라 일부가 빠지지만 ID와 이름의 대응은 바뀌지 않는다. API를 매번 치지 않도록
여기 고정해 둔다 — 값이 바뀌는 성질의 데이터가 아니다.

용도: `dcat_dataset.theme`(원천 분류 원문)를 채운다. 뉴스·블로그는 네이버 검색
API가 분류를 주지 않아 이 방식을 못 쓴다
(docs/api/01_Dataset_Registration_Scenario.md §5.2).
"""

CATEGORIES = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "18": "Short Movies",
    "19": "Travel & Events",
    "20": "Gaming",
    "21": "Videoblogging",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
    "30": "Movies",
    "31": "Anime/Animation",
    "32": "Action/Adventure",
    "33": "Classics",
    "34": "Comedy",
    "35": "Documentary",
    "36": "Drama",
    "37": "Family",
    "38": "Foreign",
    "39": "Horror",
    "40": "Sci-Fi/Fantasy",
    "41": "Thriller",
    "42": "Shorts",
    "43": "Shows",
    "44": "Trailers",
}


def name_of(category_id) -> str:
    """모르는 ID는 'YouTube:{id}'로 돌려준다 — 값을 버리지 않는다."""
    cid = str(category_id)
    return CATEGORIES.get(cid, f"YouTube:{cid}")


def topic_name(url: str) -> str:
    """topicCategories의 위키백과 URL에서 주제명만 꺼낸다.

    'https://en.wikipedia.org/wiki/Health' → 'Health'
    'https://en.wikipedia.org/wiki/Physical_fitness' → 'Physical fitness'
    """
    if not url:
        return ""
    return url.rstrip("/").rsplit("/", 1)[-1].replace("_", " ")
