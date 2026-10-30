"""임베딩 모델 래퍼 — 프로세스당 1개 로딩, 배치 인코딩.

모델은 `intfloat/multilingual-e5-base`(768차원). 규약은 ADR-016에 있다
(모델 선정 근거, 프리픽스 필수, CPU 고정, 청킹, 최대값 집계).

**프리픽스가 필수다** — 문서는 `passage: `, 질의는 `query: `. 빠뜨려도 에러가
나지 않고 검색 품질만 조용히 떨어진다. 질의는 반드시 `encode_query()`를 쓴다.

입력은 호출부에서 이미 청킹돼 들어온다(`chunker.chunk`, 기본 80자). 통짜 본문을
넘기지 않는다 — 짧은 질의 ↔ 긴 문서 비대칭에서 유사도가 무너진다.

⚠️ 디바이스는 CPU로 고정한다. Apple Silicon MPS에서 배치 인코딩 시 벡터가
손상된다(동일 텍스트 단건 대비 cos 0.0073). `self_check()`가 로딩 시 검사한다.
"""

import logging
import threading
from typing import List, Optional

from src.common import config

logger = logging.getLogger(__name__)

# 2026-10-29: paraphrase-multilingual-mpnet-base-v2 → multilingual-e5-base
#
# 이전 모델은 문장쌍 패러프레이즈용이라 짧은 질의 ↔ 긴 문서 비대칭 검색에 맞지
# 않았다. e5는 그 용도로 대조학습된 모델이다. 같은 코퍼스(1,200건)·같은 질의로
# 둘 다 청킹해 비교한 실측:
#
#   질의                  이전 모델   e5-base
#   치질 수술 후 주의사항      7위        1위
#   위암 조기 진단            4위        1위
#   HBM 고대역폭 메모리        3위        1위
#   대장내시경 검사           1위        2위
#
# 차원이 768로 같아 DDL·인덱스를 건드리지 않는다. 인코딩은 약 20% 느려진다.
#
# ⚠️ 분류(category zero-shot)에서는 두 모델이 비슷하게 나빴다(Top-1 3/8 동일).
#    모델 교체로 분류가 해결되지는 않는다 — src/database/category.py 참조.
MODEL_NAME = "intfloat/multilingual-e5-base"

# e5는 512까지 학습됐다. 이전 모델은 128이 상한이라 긴 본문이 통째로 잘렸다.
# 청킹으로 입력이 이미 짧지만(기본 80자), 상한을 모델 능력에 맞춰 둔다.
MAX_SEQ_LENGTH = 512
BATCH_SIZE = 32

# ⚠️ **e5 계열은 프리픽스가 필수다.** 빠뜨려도 에러가 나지 않고 성능만 조용히
# 떨어진다(모델카드 명시). 색인과 질의가 반드시 같은 함수를 타도록, 여기 한 곳에서만
# 붙인다 — 호출부가 직접 문자열을 이어붙이면 한쪽만 빠뜨리기 쉽다.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "

# ⚠️ **디바이스를 CPU로 고정한다.**
#
# SentenceTransformer는 Apple Silicon에서 MPS를 자동 선택하는데, **MPS에서 배치
# 인코딩을 하면 벡터가 망가진다.** 같은 문장을 단건으로 넣었을 때와 배치에 섞어
# 넣었을 때의 코사인 유사도가 1.0이어야 하는데 0.0073이 나온다(2026-10-28 실측).
#
#     [mps] 단건 vs 배치0번: 0.0073    단건 vs 단건재실행: 1.0000
#     [cpu] 단건 vs 배치0번: 1.0000    단건 vs 단건재실행: 1.0000
#
# 단건끼리는 재현되므로 비결정성이 아니라 **배치 패딩/어텐션 마스크 처리 버그**로
# 보인다. 이 때문에 첫 백필 33,875건이 전부 쓸 수 없는 값이었고, 검색하면 질의와
# 무관한 짧은 제목이 상위에 올라왔다(제목이 글자까지 같은 항목이 123위).
#
# 운영 서버는 GPU가 없어(ADR-013) 어차피 CPU다. MPS는 개발용 Mac에서만 잡힌다.
# 다른 가속기를 쓰려면 EMBEDDING_DEVICE로 명시하되, 반드시 self_check()를 통과시킬 것.
DEVICE = config.get_env("EMBEDDING_DEVICE", "cpu")

_model = None
_lock = threading.Lock()


def self_check(model) -> None:
    """배치 인코딩이 단건 인코딩과 같은 벡터를 내는지 확인한다.

    MPS 배치 버그 같은 류를 모델 로딩 시점에 잡는다. 통과 못 하면 그 디바이스로
    만든 임베딩은 전부 버려야 하므로, 조용히 넘어가지 않고 바로 실패시킨다.
    """
    probe = PASSAGE_PREFIX + "임베딩 정합성 확인용 문장"
    alone = model.encode([probe])[0]
    batched = model.encode([probe, "다른 문장 하나", "또 다른 문장"])[0]
    import numpy as np

    sim = float(
        np.dot(alone, batched)
        / (np.linalg.norm(alone) * np.linalg.norm(batched))
    )
    if sim < 0.999:
        raise RuntimeError(
            f"임베딩 자가검증 실패 — device={DEVICE!r}에서 배치 인코딩 결과가 "
            f"단건과 다릅니다(코사인 {sim:.4f}, 1.0이어야 정상).\n"
            f"  이 디바이스로 만든 벡터는 쓸 수 없습니다. "
            f"EMBEDDING_DEVICE=cpu로 두세요."
        )


def get_model():
    """모델을 지연 로딩한다. 로딩에 5초 남짓 걸리므로 쓸 때만 올린다."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("임베딩 모델 로딩: %s (device=%s)", MODEL_NAME, DEVICE)
                m = SentenceTransformer(MODEL_NAME, device=DEVICE)
                m.max_seq_length = MAX_SEQ_LENGTH
                self_check(m)
                _model = m
    return _model


def encode(texts: List[str], batch_size: Optional[int] = None,
           prefix: str = PASSAGE_PREFIX) -> List[List[float]]:
    """텍스트 목록을 768차원 벡터 목록으로. 빈 목록이면 모델도 안 올린다.

    기본 프리픽스는 `passage: ` — 호출의 대부분이 문서 색인이기 때문이다.
    질의를 임베딩할 때는 반드시 `encode_query()`를 쓴다.
    """
    if not texts:
        return []
    vectors = get_model().encode(
        [prefix + t for t in texts],
        batch_size=batch_size or BATCH_SIZE,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def encode_query(text: str) -> List[float]:
    """검색 질의 전용. `query: ` 프리픽스를 붙인다.

    문서는 `passage: `, 질의는 `query: ` — 이 둘을 섞으면 성능이 떨어진다.
    """
    return encode([text], prefix=QUERY_PREFIX)[0]
