from __future__ import annotations

from service.etl.extractor import extractor_v2
from service.etl.transform import normalizer_v2, parser_v2, chunker_v2
from service.etl.loader import jsonl_to_postgres_v2, embeddings_v2


def run_etl() -> None:
    """ETL 4단계: JSONL 산출물 생성."""
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


def run_load() -> None:
    """적재 2단계: chunks_v2 → embeddings_e5_v2."""
    print("\n=== 적재 v2 시작 ===\n")
    print("[5/6] jsonl_to_postgres_v2 — chunks_v2 테이블 upsert")
    jsonl_to_postgres_v2.main()
    print("\n[6/6] embeddings_v2 — embed_text 임베딩")
    embeddings_v2.main()
    print("\n=== 적재 v2 완료 ===")


def run() -> None:
    """전체 파이프라인: ETL + 적재 + 임베딩."""
    run_etl()
    run_load()


if __name__ == "__main__":
    run()
