"""데이터셋 공통 분류 — 디지털 집현전 주제 분류 (대분류 7 / 중분류 76).

출처: 협력기관 「데이터셋 공통 분류(category) 정의」
적용: `dcat_dataset.category` (JSONB NOT NULL DEFAULT '[]', GIN 인덱스)

값 표기는 **'대분류 > 중분류'** 이고 **구분 기호 ' > ' 앞뒤 공백은 각 1칸**이다.
중분류 명칭의 가운뎃점(`전기·전자`)과 괄호(`고등(대학)`)는 그대로 쓴다 —
임의로 정규화하면 협력기관이 넣은 값과 안 맞는다.

문서: docs/database/category_taxonomy.md
"""

from typing import Dict, List

SEP = " > "

TAXONOMY: Dict[str, List[str]] = {
    "과학": ["수학", "통계학", "물리학", "천문학", "화학", "생물학",
             "지구과학", "지질학", "대기과학", "생활과학"],
    "기술": ["기계공학", "재료공학", "화학공학", "전기·전자", "정보·통신",
             "인공지능·컴퓨팅", "에너지·자원", "원자력", "환경공학",
             "토목·건설·교통", "도시공학", "항공우주공학", "조선·해양"],
    "인문": ["문학", "언어", "철학", "종교", "심리", "역사", "지리"],
    "사회": ["공공질서·안전", "복지", "사회문제", "인권", "국토·지역개발",
             "일반공공행정", "외교", "안보국방", "경제·경영", "산업", "정치"],
    "교육": ["유아", "초등학교", "중학교", "고등학교", "고등(대학)", "해외유학",
             "특수교육", "직업·평생", "자격", "교양"],
    "의료": ["의학", "치의학", "한의학", "약학", "간호학", "공중보건", "질병관리",
             "건강검진", "재활", "요양", "의료공학", "의약품"],
    "문화": ["미술", "방송·미디어", "공예", "게임·오락", "축제·전시", "연극", "무용",
             "영상·영화", "음악", "디자인", "사진", "만화", "스포츠"],
}

# '대분류 > 중분류' 전체 목록 (76개)
ALL_CATEGORIES: List[str] = [
    f"{major}{SEP}{minor}" for major, minors in TAXONOMY.items() for minor in minors
]

# 데이터셋당 부여 개수 상한 (협력기관 규칙: 1~3개, 첫 번째가 대표 분류)
MAX_PER_DATASET = 3


def is_valid(value: str) -> bool:
    """분류표에 있는 값인가. 표 밖의 값은 넣지 않는다(협력기관 규칙)."""
    return value in ALL_CATEGORIES


def major_of(value: str) -> str:
    """'의료 > 공중보건' → '의료'."""
    return value.split(SEP, 1)[0] if SEP in value else ""


def validate(values: List[str]) -> List[str]:
    """표에 있는 값만, 중복 없이, 최대 3개까지 남긴다.

    협력기관 규칙: 데이터셋당 1~3개, 첫 번째가 대표 분류, 표에 있는 값만,
    같은 값 중복 불가. 순서(대표성)는 보존한다.
    """
    out: List[str] = []
    for v in values:
        if is_valid(v) and v not in out:
            out.append(v)
        if len(out) >= MAX_PER_DATASET:
            break
    return out
