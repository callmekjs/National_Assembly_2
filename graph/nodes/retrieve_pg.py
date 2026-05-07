from graph.state import QAState
from service.rag.retrieval.retriever import Retriever
from service.rag.models.config import EmbeddingModelType

retriever = Retriever(model_type=EmbeddingModelType.MULTILINGUAL_E5_SMALL, enable_temporal_filter=False)


def run(state: QAState) -> QAState:
    query = state.get("rewritten_query") or state.get("question", "")
    top_k = state.get("meta", {}).get("top_k", 5)
    results = retriever.search(query=query, top_k=top_k, include_metadata=True)
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
