from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector

from service.rag.models.config import EmbeddingModelType
from service.rag.models.encoder import EmbeddingEncoder

ROOT = Path(__file__).resolve().parents[3]

UPSERT_SQL = """
INSERT INTO embeddings_e5_v2 (chunk_id, embedding)
VALUES (%s, %s)
ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
"""


def _connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )
    register_vector(conn)
    return conn


def _parse_db_row(row: tuple) -> dict:
    return {"id": row[0], "chunk_id": row[1], "embed_text": row[2]}


def _build_count_sql(skip_existing: bool) -> str:
    if skip_existing:
        return """
        SELECT COUNT(*)
        FROM chunks_v2 c
        LEFT JOIN embeddings_e5_v2 e ON e.chunk_id = c.chunk_id
        WHERE c.section_type = 'body'
          AND e.chunk_id IS NULL
        """
    return "SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body'"


def _build_iter_sql(skip_existing: bool, limit: int | None) -> str:
    if skip_existing:
        sql = """
        SELECT c.id, c.chunk_id, c.embed_text
        FROM chunks_v2 c
        LEFT JOIN embeddings_e5_v2 e ON e.chunk_id = c.chunk_id
        WHERE c.section_type = 'body'
          AND e.chunk_id IS NULL
        ORDER BY c.id
        """
    else:
        sql = """
        SELECT id, chunk_id, embed_text
        FROM chunks_v2
        WHERE section_type = 'body'
        ORDER BY id
        """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql


def run(
    limit: int | None = None,
    batch_size: int = 100,
    force: bool = False,
) -> dict:
    """embed_text 임베딩 실행. 반환값: {"embedded": int, "skipped": int}"""
    conn = _connect()
    encoder = EmbeddingEncoder(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    skip_existing = not force
    with conn.cursor() as cur:
        cur.execute(_build_count_sql(skip_existing=True))
        total_pending = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body'")
        total_all = int(cur.fetchone()[0])
    skipped = total_all - total_pending

    if total_pending == 0:
        print("[embed_v2] 미임베딩 청크 없음 — 모두 최신 상태입니다.")
        conn.close()
        return {"embedded": 0, "skipped": skipped}

    mode = "전체 재임베딩" if force else "신규 청크만"
    print(f"[embed_v2] {mode} | 대상: {total_pending}개")

    iter_sql = _build_iter_sql(skip_existing=skip_existing, limit=limit)
    batch: list[dict] = []
    processed = 0
    batch_num = 0

    with conn.cursor() as cur:
        cur.execute(iter_sql)
        while True:
            rows = cur.fetchmany(200)
            if not rows:
                break
            for row in rows:
                batch.append(_parse_db_row(row))
                if len(batch) >= batch_size:
                    _flush(batch, encoder, conn, batch_num := batch_num + 1)
                    processed += len(batch)
                    batch = []

    if batch:
        _flush(batch, encoder, conn, batch_num + 1)
        processed += len(batch)

    print(f"[embed_v2] done total_embedded={processed}")
    conn.close()
    return {"embedded": processed, "skipped": skipped}


def _flush(
    batch: list[dict],
    encoder: EmbeddingEncoder,
    conn: psycopg2.extensions.connection,
    batch_num: int,
) -> None:
    chunk_ids = [c["chunk_id"] for c in batch]
    texts = [c["embed_text"] for c in batch]
    vectors = encoder.encode_documents(texts, batch_size=len(texts))
    if len(vectors) != len(chunk_ids):
        raise RuntimeError(
            f"[embed_v2] encoder returned {len(vectors)} vectors for {len(chunk_ids)} chunks"
        )
    rows = list(zip(chunk_ids, vectors))
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, rows)
    conn.commit()
    print(f"[embed_v2] batch {batch_num}: upsert={len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(limit=args.limit, batch_size=args.batch_size, force=args.force)


if __name__ == "__main__":
    main()
