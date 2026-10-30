"""임베딩 입력 텍스트를 청크로 쪼갠다.

**왜 쪼개는가.** 모델(`paraphrase-multilingual-mpnet-base-v2`)은 문장쌍
패러프레이즈용으로 학습됐고 평균 풀링이라, 짧은 질의와 긴 문서를 비교하면
유사도가 무너진다. 2026-10-29 실측:

    질의 "위암 수술 후 관리"
      문서 앞 10자 (= 질의와 동일)                cos 1.0000
      문서 앞 20자 "…. 08.위암 수술"               cos 0.8313
      문서 앞 40자 (+ "김희성 교수 / 서울아산병원")  cos 0.0292   ← 무너짐
      무관한 문장 ("고양이 사진")                   cos 0.0832

문서 60자를 덧붙이는 것만으로 무관한 문장보다 낮아진다. 제목이 글자까지 같은
영상이 29,029건 중 17,449위였다.

문장/줄 단위로 쪼개 청크별로 임베딩하고 검색에서 **청크 최대 유사도**를 쓰면
정답이 1위로 올라온다(실측 1.0000).

**크기 선택.** `max_seq_length`가 128토큰(한국어 60~90자)이므로 그보다 긴
청크는 뒷부분이 잘려 버려진다. 기본 80자는 그 안에 들어가면서, 문장 하나가
통째로 담기는 크기다.
"""

import re
from typing import List

# 문장 끝으로 볼 구분자. 줄바꿈도 문장 경계로 취급한다 — 영상 설명·블로그 본문은
# 마침표 없이 줄바꿈만으로 끊는 경우가 흔하다.
_SPLIT = re.compile(r"(?<=[.!?])\s+|[\n\r]+")

DEFAULT_SIZE = 80
MIN_SIZE = 8  # 이보다 짧은 조각은 앞 청크에 붙인다 — "21'55\"" 같은 파편 방지


def chunk(text: str, size: int = DEFAULT_SIZE) -> List[str]:
    """텍스트를 청크 목록으로. 입력이 비면 빈 목록.

    1) 문장·줄 단위로 끊는다
    2) size를 넘는 조각은 size자로 다시 자른다 (긴 문장 대비)
    3) 너무 짧은 조각은 앞 청크에 합친다
    4) 중복 청크는 제거한다 — 제목이 설명 첫 줄에 반복되는 경우가 흔하다

    순서는 원문 순서를 지킨다. chunk_index가 그 순서다.
    """
    if not text or not text.strip():
        return []

    pieces: List[str] = []
    for part in _SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        if len(part) <= size:
            pieces.append(part)
        else:
            pieces.extend(part[i:i + size] for i in range(0, len(part), size))

    merged: List[str] = []
    for p in pieces:
        if merged and len(p) < MIN_SIZE and len(merged[-1]) + len(p) + 1 <= size:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)

    seen = set()
    out = []
    for m in merged:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out
