from __future__ import annotations

from service.etl.extractor import extractor_v2
from service.etl.transform import normalizer_v2, parser_v2, chunker_v2


def run() -> None:
    print("=== ETL v2 파이프라인 시작 ===\n")
    print("[1/4] extractor_v2 — page별 raw_text 추출")
    extractor_v2.main()
    print("\n[2/4] normalizer_v2 — 잡음 제거 + section_type")
    normalizer_v2.main()
    print("\n[3/4] parser_v2 — speaker turn 구조화")
    parser_v2.main()
    print("\n[4/4] chunker_v2 — 짧은 turn 병합 + embed_text")
    chunker_v2.main()
    print("\n=== ETL v2 완료 ===")


if __name__ == "__main__":
    run()
