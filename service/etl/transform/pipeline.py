from __future__ import annotations

from pathlib import Path
from . import parser, normalizer, chunker

ROOT = Path(__file__).resolve().parents[3]


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.open(encoding="utf-8") if line.strip())


def main():
    from service.etl.run_tracker import PipelineRun
    run = PipelineRun()

    parser.main()
    normalizer.main()
    chunker.main()
    print("[pipeline] completed: parser -> normalizer -> chunker")

    # 단계별 카운트 기록
    run.record_extract(_count_jsonl(ROOT / "data/extract/extracted.jsonl"))
    run.record_transform(_count_jsonl(ROOT / "data/transform/final/chunks.jsonl"))

    # 스키마 계약 검증
    from service.etl.contract import validate_pipeline
    ok = validate_pipeline(ROOT)
    run.record_contract(ok)

    # 품질 지표 측정
    from service.etl.quality import run_report
    report = run_report()
    run.record_quality(report)

    # 실행 이력 저장
    run.save()


if __name__ == "__main__":
    main()
