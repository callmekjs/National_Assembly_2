from __future__ import annotations

import argparse

from service.rag.models.config import EmbeddingModelType
from service.rag.models.encoder import EmbeddingEncoder
from service.rag.vectorstore.pgvector_store import PgVectorStore


def run(limit: int | None = None, batch_size: int = 100) -> None:
    encoder = EmbeddingEncoder(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    store = PgVectorStore()

    query = "SELECT chunk_id, text FROM chunks ORDER BY id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    with store.conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        chunk_ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]
        vectors = encoder.encode_documents(texts, batch_size=len(texts))
        store.insert_embeddings(EmbeddingModelType.MULTILINGUAL_E5_SMALL, chunk_ids, vectors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    run(limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
