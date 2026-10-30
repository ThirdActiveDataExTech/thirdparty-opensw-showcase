"""임베딩 입력 텍스트를 청크로 쪼갠다.

**왜 쪼개는가.** 긴 문서를 통째로 임베딩하면 짧은 질의와의 비대칭 때문에
유사도가 무너진다. 2026-10-29 실측(교체 전 모델 기준):

    질의 "위암 수술 후 관리"
      문서 앞 10자 (= 질의와 동일)                cos 1.0000
      문서 앞 40자 (+ "김희성 교수 / 서울아산병원")  cos 0.0292   ← 무너짐
      무관한 문장 ("고양이 사진")                   cos 0.0832

제목이 글자까지 같은 영상이 29,029건 중 17,449위였다. 문장/줄 단위로 쪼개고
검색에서 **청크 최대 유사도**를 쓰면 정답이 1위로 올라온다(실측 1.0000).

**크기 선택.** 기본 80자는 문장 하나가 통째로 담기는 크기다. 모델
(multilingual-e5-base)의 상한은 512토큰이라 여유가 있다.

**버리는 청크.** 청크 최대 유사도는 "가장 잘 맞는 청크 하나"로 문서 점수를
정한다. 따라서 **아무 질의에나 어중간하게 맞는 청크 하나가 문서 전체를
끌어올린다.** 2026-10-30에 실제로 관측했다 — 모든 기사에 붙는 저작권 안내
문구가 질의와 무관하게 0.8547을 찍어, `"전기차 보조금"` 검색 상위가 전부
무관한 기사로 채워졌다. 그래서 아래 두 종류를 청크 단계에서 버린다.

    1. 의미 없는 파편  — `.`, `다.`, `▁▁▁▁▁` 같은 것
    2. 정형 안내 문구  — 저작권 고지, 공유 안내 등 (_BOILERPLATE)

2번은 패턴 목록이라 원천이 늘면 함께 늘려야 한다. 채널 설명란의 공통 문구
(주소·인사말)처럼 패턴으로 잡기 어려운 중복은 남는다 —
`scripts/report_duplicate_chunks.py`로 주기적으로 확인한다.
"""

import re
from typing import List

# 문장 끝으로 볼 구분자. 줄바꿈도 문장 경계로 취급한다 — 영상 설명·블로그 본문은
# 마침표 없이 줄바꿈만으로 끊는 경우가 흔하다.
_SPLIT = re.compile(r"(?<=[.!?])\s+|[\n\r]+")

DEFAULT_SIZE = 80
MIN_SIZE = 8  # 이보다 짧은 조각은 앞 청크에 붙인다 — "21'55\"" 같은 파편 방지

# 글자·숫자가 하나라도 있어야 의미 있는 청크로 본다
_ALNUM = re.compile(r"[0-9A-Za-z가-힣]")

# 같은 문자가 반복된 구분선 — 영상 설명란에 흔하다 ("▁▁▁▁▁", "-----")
_RULE = re.compile(r"^(.)\1{3,}$")

# 본문이 아니라 매체가 모든 글에 붙이는 고정 문구.
# 질의와 무관하게 중간 정도 유사도를 내서 최대값 집계를 교란한다.
_BOILERPLATE = re.compile(
    r"저작권자|무단\s*전재|재배포\s*금지|All rights reserved|이 기사를 공유합니다",
    re.IGNORECASE,
)


def _is_noise(text: str) -> bool:
    """버릴 청크인지. 의미 없는 파편이거나 매체 고정 문구면 True."""
    t = text.strip()
    if len(t) < MIN_SIZE or not _ALNUM.search(t):
        return True
    if _RULE.match(t):
        return True
    return bool(_BOILERPLATE.search(t))


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
        # 짧은 조각은 앞 청크에 붙인다. **크기 상한을 넘겨도 붙인다** —
        # 앞 청크가 이미 size에 가까우면 붙이지 못해 "." 같은 파편이 독립
        # 청크로 남았다(뉴스 36,242청크 중 1,180개가 8자 미만이었다).
        # 80자가 85자가 되는 것은 모델 상한 512토큰에 한참 못 미쳐 무해하다.
        if merged and len(p) < MIN_SIZE:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)

    seen = set()
    out = []
    for m in merged:
        if m not in seen and not _is_noise(m):
            seen.add(m)
            out.append(m)
    return out
