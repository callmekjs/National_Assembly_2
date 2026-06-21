from graph.state import QAState
from service.rag.retrieval.date_range import normalize_meeting_date_range
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
    date_from, date_to = normalize_meeting_date_range(
        str(date_from) if date_from else None,
        str(date_to) if date_to else None,
    )
    use_reranker = bool(meta.get("use_reranker", False))
    balance_speakers = bool(meta.get("balance_speakers", False))
    candidate_multiplier = int(meta.get("candidate_multiplier", 50))
    use_multi_query = bool(meta.get("use_multi_query", False))
    multi_query_variants = int(meta.get("multi_query_variants", 3))
    use_hyde = bool(meta.get("use_hyde", False))
    use_parent_doc = bool(meta.get("use_parent_doc", False))
    parent_doc_window = int(meta.get("parent_doc_window", 1))
    use_compression = bool(meta.get("use_compression", False))
    use_step_back = bool(meta.get("use_step_back", False))
    use_fusion = bool(meta.get("use_fusion", False))
    use_neural_reranker = bool(meta.get("use_neural_reranker", False))
    use_llm_reranker = bool(meta.get("use_llm_reranker", False))
    use_mmr = bool(meta.get("use_mmr", False))
    mmr_lambda = float(meta.get("mmr_lambda", 0.7))
    use_score_norm = bool(meta.get("use_score_norm", False))
    use_ensemble_reranker = bool(meta.get("use_ensemble_reranker", False))
    eval_recall = bool(meta.get("eval_recall", False))
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
        use_multi_query=use_multi_query,
        multi_query_variants=multi_query_variants,
        use_hyde=use_hyde,
        use_parent_doc=use_parent_doc,
        parent_doc_window=parent_doc_window,
        use_compression=use_compression,
        use_step_back=use_step_back,
        use_fusion=use_fusion,
        use_neural_reranker=use_neural_reranker,
        use_llm_reranker=use_llm_reranker,
        use_mmr=use_mmr,
        mmr_lambda=mmr_lambda,
        use_score_norm=use_score_norm,
        use_ensemble_reranker=use_ensemble_reranker,
        eval_recall=eval_recall,
    )
    state["retrieval_empty"] = len(results) == 0
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
