from __future__ import annotations

import re

from service.rag.models.encoder import EmbeddingEncoder
from service.rag.models.config import EmbeddingModelType
from service.rag.retrieval.reranker import create_default_reranker
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
        alpha: float = 0.8,
        committee: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_metadata: bool = True,
        use_reranker: bool = False,
        include_context: bool = True,
        balance_speakers: bool = False,
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
            lexical_score = self._lexical_overlap_score(query, row.content)
            alpha = max(0.0, min(1.0, alpha))
            hybrid_score = alpha * float(row.similarity) + (1.0 - alpha) * lexical_score
            out.append(
                {
                    "content": row.content,
                    "chunk_id": row.chunk_id,
                    "source_id": row.source_id,
                    "date": row.metadata.get("meeting_date", ""),
                    "title": row.metadata.get("section", ""),
                    "url": row.metadata.get("url", ""),
                    "similarity": row.similarity,
                    "lexical_score": lexical_score,
                    "hybrid_score": hybrid_score,
                    "metadata": row.metadata if include_metadata else {},
                }
            )
        out = sorted(out, key=lambda x: x.get("hybrid_score", x.get("similarity", 0.0)), reverse=True)
        if use_reranker and out:
            reranker = create_default_reranker()
            out = reranker.rerank(query, out, top_k=top_k)
        if balance_speakers and out:
            out = self._balance_speakers(out, top_k)
        else:
            out = out[:top_k]
        return out

    def _lexical_overlap_score(self, query: str, content: str) -> float:
        query_tokens = {t for t in re.findall(r"[가-힣a-zA-Z0-9]+", (query or "").lower()) if len(t) >= 2}
        content_tokens = {t for t in re.findall(r"[가-힣a-zA-Z0-9]+", (content or "").lower()) if len(t) >= 2}
        if not query_tokens:
            return 0.0
        overlap = len(query_tokens.intersection(content_tokens))
        return overlap / float(len(query_tokens))

    def _balance_speakers(self, docs: list[dict], top_k: int) -> list[dict]:
        selected: list[dict] = []
        seen_chunk_ids: set[str] = set()
        speaker_bucket: dict[str, list[dict]] = {}
        for doc in docs:
            speaker = str((doc.get("metadata") or {}).get("speaker", "")).strip() or "UNKNOWN"
            speaker_bucket.setdefault(speaker, []).append(doc)

        # round-robin으로 speaker 다양성을 유지해 편향을 줄인다.
        speakers = list(speaker_bucket.keys())
        idx_map = {s: 0 for s in speakers}
        while len(selected) < top_k:
            progressed = False
            for speaker in speakers:
                i = idx_map[speaker]
                bucket = speaker_bucket[speaker]
                if i >= len(bucket):
                    continue
                candidate = bucket[i]
                idx_map[speaker] += 1
                cid = str(candidate.get("chunk_id", ""))
                if cid in seen_chunk_ids:
                    continue
                selected.append(candidate)
                seen_chunk_ids.add(cid)
                progressed = True
                if len(selected) >= top_k:
                    break
            if not progressed:
                break
        return selected[:top_k]
