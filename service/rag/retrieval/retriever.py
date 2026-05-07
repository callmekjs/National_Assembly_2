from __future__ import annotations

from service.rag.models.encoder import EmbeddingEncoder
from service.rag.models.config import EmbeddingModelType
from service.rag.vectorstore.pgvector_store import PgVectorStore


class Retriever:
    def __init__(self, model_type: EmbeddingModelType, enable_temporal_filter: bool = False):
        self.model_type = model_type
        self.enable_temporal_filter = enable_temporal_filter
        self.encoder = EmbeddingEncoder(model_type)
        self.store = PgVectorStore()

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
        committee: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_metadata: bool = True,
        use_reranker: bool = False,
        include_context: bool = True,
    ) -> list[dict]:
        vector = self.encoder.encode_query(query)
        filters = {
            "committee": committee or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
        }
        rows = self.store.search_similar(vector, top_k=top_k, filters=filters)
        out: list[dict] = []
        for row in rows:
            if row.similarity < min_similarity:
                continue
            out.append(
                {
                    "content": row.content,
                    "chunk_id": row.chunk_id,
                    "source_id": row.source_id,
                    "date": row.metadata.get("meeting_date", ""),
                    "title": row.metadata.get("section", ""),
                    "url": row.metadata.get("url", ""),
                    "similarity": row.similarity,
                    "metadata": row.metadata if include_metadata else {},
                }
            )
        return out
