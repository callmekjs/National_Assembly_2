from __future__ import annotations

import argparse

from service.rag.models.config import EmbeddingModelType
from service.rag.models.encoder import EmbeddingEncoder
from service.rag.vectorstore.pgvector_store import PgVectorStore


def run(
    limit: int | None = None,
    batch_size: int = 100,
    force: bool = False,
) -> dict:
    """임베딩 실행. 반환값: {"embedded": int, "skipped": int}"""
    encoder = EmbeddingEncoder(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    store = PgVectorStore()

    skip_existing = not force
    total_pending = store.count_chunks_to_process(skip_existing=skip_existing)
    total_all = store.count_chunks_to_process(skip_existing=False)
    skipped = total_all - total_pending

    if total_pending == 0:
        print("[load_vector] 미임베딩 청크 없음 — 모두 최신 상태입니다.")
        return {"embedded": 0, "skipped": skipped}

    mode = "전체 재임베딩" if force else "신규 청크만"
    print(f"[load_vector] {mode} | 대상: {total_pending}개")

    batch: list[dict] = []
    processed = 0
    batch_num = 0

    for chunk in store.iter_chunks_to_process(skip_existing=skip_existing, limit=limit):
        batch.append(chunk)
        if len(batch) >= batch_size:
            _flush(batch, encoder, store, batch_num := batch_num + 1)
            processed += len(batch)
            batch = []

    if batch:
        _flush(batch, encoder, store, batch_num + 1)
        processed += len(batch)

    print(f"[load_vector] done total_embedded={processed}")
    return {"embedded": processed, "skipped": skipped}


def _flush(batch: list[dict], encoder: EmbeddingEncoder, store: PgVectorStore, batch_num: int) -> None:
    chunk_ids = [c["chunk_id"] for c in batch]
    texts = [c["natural_text"] for c in batch]
    vectors = encoder.encode_documents(texts, batch_size=len(texts))
    n = store.insert_embeddings(EmbeddingModelType.MULTILINGUAL_E5_SMALL, chunk_ids, vectors)
    print(f"[load_vector] batch {batch_num}: embeddings_upsert={n}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--force", action="store_true", help="이미 임베딩된 청크도 재처리")
    args = parser.parse_args()
    run(limit=args.limit, batch_size=args.batch_size, force=args.force)


if __name__ == "__main__":
    main()
