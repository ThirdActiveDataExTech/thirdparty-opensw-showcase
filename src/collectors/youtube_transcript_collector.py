"""YouTube 영상 트랜스크립트 — 자체 STT 방식 (architecture/05_Object_Storage_Export.md §4 확정).

레거시 `youtube_transcript_extractor.py`(youtube-transcript-api, 비공식 timedtext
엔드포인트 직접 호출)는 IP 평판 기반 차단이 확인돼(요청 빈도를 낮춰도 동일) 채택하지
않는다. 대신 `yt-dlp`로 오디오만 내려받고(자막 스크래핑이 아니라 일반 다운로드
기능이라 timedtext류 엔드포인트를 안 거침) `faster-whisper`로 로컬 전사한다 — YouTube의
자막 제공 여부/차단 문제와 완전히 무관해진다.

모델은 §4.4 확정대로 small/INT8/CPU(GPU 없는 서버 기준), 최초 호출 시 1회만 로드해
재사용한다(모델 가중치는 HuggingFace Hub에서 최초 다운로드 — 서버 인터넷 egress 필요).
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6)
    return _model


def download_audio(video_id: str, tmp_dir: str) -> Optional[str]:
    """오디오만 다운로드해 mp3 경로를 반환. 실패(비공개/삭제 영상 등) 시 None."""
    import yt_dlp

    output_template = str(Path(tmp_dir) / f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # 2025년 하반기부터 YouTube의 봇 감지 강화로 기본(web) 클라이언트가
        # "The page needs to be reloaded" 에러로 막히는 사례가 흔해짐 — android 클라이언트로
        # 우회 (자막 스크래핑이 아니라 일반 다운로드 경로라 이 우회는 §4의 IP 차단 문제와는
        # 무관, 단순히 요청을 어떤 클라이언트로 위장하느냐의 문제)
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://youtube.com/watch?v={video_id}"])
    except Exception as e:
        logger.warning(f"오디오 다운로드 실패 (video_id={video_id}): {e}")
        return None

    audio_path = Path(tmp_dir) / f"{video_id}.mp3"
    return str(audio_path) if audio_path.exists() else None


def transcribe(audio_path: str) -> Tuple[List[Dict[str, Any]], str, str]:
    """세그먼트 리스트 + 전체 텍스트 + 감지된 언어. §4.5 raw 파일 스키마의 core.

    language를 강제 지정하지 않고 자동 감지한다 — 이 콜렉터는 특정 언어 채널
    전용이 아니라 임의 YouTube 채널을 대상으로 하므로("ko"로 고정했을 때 영어
    채널 등에서 품질이 크게 떨어지는 걸 실측으로 확인, 2026-07-27) 매 영상마다
    Whisper가 첫 30초로 판별한 실제 언어를 그대로 쓴다.
    """
    model = _get_model()
    segments_iter, info = model.transcribe(audio_path)
    segments = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments_iter]
    full_text = " ".join(s["text"] for s in segments if s["text"])
    return segments, full_text, info.language


def fetch_transcript(video_id: str) -> Optional[Tuple[List[Dict[str, Any]], str, str]]:
    """오디오 다운로드+전사를 묶은 최상위 진입점.

    트랜스크립트는 부가 기능이므로 어떤 이유로든 실패하면 예외를 삼키고 None을
    반환한다 — 호출부(파이프라인)가 이 실패로 영상 메타 수집 자체를 막으면 안 된다.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = download_audio(video_id, tmp_dir)
            if audio_path is None:
                return None
            return transcribe(audio_path)
    except Exception as e:
        logger.warning(f"트랜스크립트 처리 실패 (video_id={video_id}): {e}")
        return None
