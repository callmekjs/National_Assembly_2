"""
Day 13: 무필터·날짜 엣지·적재 건수 정합 스모크.

  python -m service.rag.smoke_day13 --pg-port 5433

DB 미기동 시 실패(종료 코드 1).
"""
from __future__ import annotations

import argparse
import os
import sys

from service.rag.models.config import EmbeddingModelType
from service.rag.retrieval.date_range import normalize_meeting_date_range
from service.rag.retrieval.retriever import Retriever


def _counts(pg_port: str) -> tuple[int, int, int]:
    import psycopg2

    os.environ["PG_PORT"] = str(pg_port)
    from config.vector_database import get_vector_db_config

    cfg = get_vector_db_config().get_db_config()
    conn = psycopg2.connect(**cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            n_chunks = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM embeddings_e5")
            n_emb = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT COUNT(*) FROM chunks c
                LEFT JOIN embeddings_e5 e ON e.chunk_id = c.chunk_id
                WHERE e.chunk_id IS NULL
                """
            )
            n_missing = int(cur.fetchone()[0])
    finally:
        conn.close()
    return n_chunks, n_emb, n_missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 13 데이터·도메인 확장 스모크")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    parser.add_argument("--query", default="대북정책 핵심 쟁점은?")
    args = parser.parse_args()

    os.environ["PG_PORT"] = str(args.pg_port)

    print("[smoke_day13] PG_PORT=", os.environ["PG_PORT"])

    n_chunks, n_emb, n_missing = _counts(args.pg_port)
    print(f"[smoke_day13] chunks={n_chunks} embeddings_e5={n_emb} chunks_without_embedding={n_missing}")
    if n_chunks != n_emb or n_missing != 0:
        print(
            "[smoke_day13] FAIL: chunks와 embeddings_e5 건수 불일치 또는 미임베딩 행 존재",
            file=sys.stderr,
        )
        return 1

    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    scenarios = [
        ("no_committee_no_dates", dict(committee=None, date_from=None, date_to=None)),
        ("committee_foreign_affairs", dict(committee="외교통일위원회", date_from=None, date_to=None)),
        ("dates_empty_strings", dict(committee=None, date_from="", date_to="")),
        ("dates_inverted_then_normalized", dict(committee=None, date_from="2099-12-31", date_to="2000-01-01")),
    ]

    for label, kw in scenarios:
        df, dt = normalize_meeting_date_range(kw.get("date_from"), kw.get("date_to"))
        res = retriever.search(
            args.query,
            top_k=5,
            alpha=0.75,
            committee=kw.get("committee"),
            date_from=df,
            date_to=dt,
            candidate_multiplier=8,
        )
        n = len(res)
        print(f"[smoke_day13] {label}: hits={n}")
        if n < 1:
            print(f"[smoke_day13] FAIL: Search hits < 1 ({label})", file=sys.stderr)
            return 1

    print("[smoke_day13] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
