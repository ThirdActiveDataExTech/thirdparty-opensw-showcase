"""CLI 진입점 — 수동 검증용.

사용법:
    python -m src.main run <dataset_id>

Airflow 도입(§6.2, Phase 2) 전까지는 이 CLI로 수동/K8s CronJob 실행을 한다.
dataset_id의 source_type을 보고 알맞은 pipelines/{source}.run()으로 위임한다 —
ADR-002/007이 요구하는 "오케스트레이터 무관 run(dataset_id)" 계약 그대로.
"""

import sys
from typing import Optional

from src.common.config import TRIGGERED_BY
from src.database.db import get_conn

PIPELINE_MODULES = {
    "video": "src.pipelines.youtube_pipeline",
    "shopping_insight": "src.pipelines.naver_shopping_pipeline",
    "persona_insight": "src.pipelines.naver_persona_pipeline",
    "news": "src.pipelines.naver_news_pipeline",
    "blog": "src.pipelines.naver_blog_pipeline",
}


def _get_source_type(dataset_id: str) -> str:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT source_type FROM dcat_dataset WHERE dataset_id = %s", (dataset_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"dcat_dataset에 dataset_id={dataset_id!r} 없음")
        return row[0]
    finally:
        conn.close()


def run_dataset(dataset_id: str, triggered_by: Optional[str] = None) -> None:
    source_type = _get_source_type(dataset_id)
    module_path = PIPELINE_MODULES.get(source_type)
    if module_path is None:
        raise NotImplementedError(
            f"지원하지 않는 source_type={source_type!r} (PIPELINE_MODULES 미등록)"
        )
    import importlib

    pipeline = importlib.import_module(module_path)
    pipeline.run(dataset_id, triggered_by or TRIGGERED_BY)


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        print("사용법: python -m src.main run <dataset_id>")
        sys.exit(1)
    dataset_id = sys.argv[2]
    run_dataset(dataset_id)
    print(f"완료: {dataset_id}")


if __name__ == "__main__":
    main()
