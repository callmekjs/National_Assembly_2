from graph.state import QAState
from service.rag.retrieval.retriever import Retriever
from service.rag.models.config import EmbeddingModelType

retriever = Retriever(model_type=EmbeddingModelType.MULTILINGUAL_E5_SMALL, enable_temporal_filter=False)


def run(state: QAState) -> QAState:
    query = state.get("rewritten_query") or state.get("question", "")
    meta = state.get("meta") or {}
    top_k = int(meta.get("top_k", 5))
    alpha = float(meta.get("alpha", 0.8))
    committee_raw = meta.get("committee")
    committee = (str(committee_raw).strip() if committee_raw is not None else "") or None
    date_from = meta.get("date_from") or None
    date_to = meta.get("date_to") or None
    if isinstance(date_from, str) and not date_from.strip():
        date_from = None
    if isinstance(date_to, str) and not date_to.strip():
        date_to = None
    use_reranker = bool(meta.get("use_reranker", False))
    balance_speakers = bool(meta.get("balance_speakers", False))
    candidate_multiplier = int(meta.get("candidate_multiplier", 50))
    results = retriever.search(
        query=query,
        top_k=top_k,
        alpha=alpha,
        committee=committee,
        date_from=date_from,
        date_to=date_to,
        include_metadata=True,
        use_reranker=use_reranker,
        balance_speakers=balance_speakers,
        candidate_multiplier=candidate_multiplier,
    )
    state["retrieved"] = [
        {
            "chunk_text": r.get("content", ""),
            "source_id": r.get("source_id", ""),
            "date": r.get("date", ""),
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "chunk_id": r.get("chunk_id", ""),
            "similarity": r.get("similarity", 0.0),
            "metadata": r.get("metadata", {}),
        }
        for r in results
    ]
    return state
