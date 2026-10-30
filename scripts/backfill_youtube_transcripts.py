"""기존 YouTube 영상 트랜스크립트 소급 처리 (1회성 백로그 스크립트).

architecture/05_Object_Storage_Export.md §4.4 — 이 기능(자체 STT) 배포 이전에 이미
수집된 영상은 트랜스크립트가 없다. 정기 수집(`run()`)은 신규 발견 영상만 처리하므로
이 기존 백로그는 별도로 훑어야 한다. `meta_video.has_transcript=FALSE`인
영상을 대상으로 하며, 재실행해도 이미 처리된 영상은 건너뛴다(멱등).

처리 속도 (2026-10-29 실측, faster-whisper small / CPU int8 / 6스레드):
  **영상 길이의 약 1/3 시간**이 든다(평균 3.0배속). 전사가 88%, 다운로드가 12%.
    90초 영상 → 33초 · 300초 → 84초 · 900초 → 282초
  코퍼스 중앙값이 3분이므로 **건당 약 46초**, 8시간 배치면 약 620건.

사용 예:
  # 야간 배치 — 8시간 예산 (운영 권장)
  PYTHONPATH=. python scripts/backfill_youtube_transcripts.py --limit 2000 --budget-sec 28800

  # 파일럿
  PYTHONPATH=. python scripts/backfill_youtube_transcripts.py --limit 10

  # 특정 데이터셋만
  PYTHONPATH=. python scripts/backfill_youtube_transcripts.py --dataset-id urn:youtube:dataset_358414 --limit 5

수집 파이프라인도 자체 예산(YOUTUBE_TRANSCRIPT_BUDGET_SEC, 기본 600초)으로 신규
유입분을 따라간다. 이 스크립트는 **기존 백로그를 터는 용도**다 — 둘 다
has_transcript=FALSE를 대상으로 하므로 겹쳐 돌아도 중복 처리되지 않는다.
"""

import argparse
import time
from datetime import datetime, timezone

from src.collectors import youtube_transcript_collector
from src.database import meta_video
from src.storage import raw_export


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=10, help="이번 실행에서 처리할 영상 수 (기본 10)")
    parser.add_argument("--dataset-id", default=None, help="지정 시 그 데이터셋만, 생략 시 전체")
    parser.add_argument(
        "--budget-sec", type=int, default=None,
        help="처리에 쓸 최대 시간(초). 야간 배치용 — 지정하면 이 시간을 넘기는 순간 "
             "남은 대상을 두고 멈춘다. --limit과 함께 주면 둘 중 먼저 걸리는 쪽.",
    )
    args = parser.parse_args()

    targets = meta_video.get_untranscribed(dataset_id=args.dataset_id, limit=args.limit)
    if not targets:
        print("처리할 대상 없음 (모든 영상에 이미 트랜스크립트가 있거나 대상 데이터셋에 영상 없음)")
        return

    deadline = time.monotonic() + args.budget_sec if args.budget_sec else None
    print(f"대상 {len(targets)}개" + (f" / 예산 {args.budget_sec}초" if deadline else ""))
    success, failed = 0, 0
    for i, video in enumerate(targets, 1):
        if deadline and time.monotonic() >= deadline:
            print(f"예산 소진 — 남은 {len(targets) - i + 1}개는 다음 실행에서 처리")
            break
        t0 = time.time()
        try:
            result = youtube_transcript_collector.fetch_transcript(video["video_id"])
        except Exception as e:
            # 비공개 전환·지역 제한 등으로 오디오를 못 받는 경우가 흔하다.
            # 한 건 때문에 배치 전체를 멈추지 않는다.
            print(f"[{i}/{len(targets)}] {video['video_id']} — 오류: {type(e).__name__}: {str(e)[:60]}")
            failed += 1
            continue
        elapsed = time.time() - t0

        if result is None:
            print(f"[{i}/{len(targets)}] {video['video_id']} — 실패 ({elapsed:.1f}s)")
            failed += 1
            continue

        segments, full_text, language = result
        raw_export.write_video_transcript(video["dataset_id"], video["video_id"], segments, full_text, language)
        meta_video.mark_transcribed(video["id"], transcribed_at=datetime.now(timezone.utc))
        print(
            f"[{i}/{len(targets)}] {video['video_id']} — 성공 ({elapsed:.1f}s, "
            f"language={language}, segments={len(segments)})"
        )
        success += 1

    print(f"완료: 성공 {success} / 실패 {failed} / 전체 {len(targets)}")


if __name__ == "__main__":
    main()
