from __future__ import annotations

from graph.state import QAState


def run(state: QAState) -> QAState:
    docs = state.get("reranked") or state.get("retrieved", [])
    state["context"] = "\n\n".join((d.get("chunk_text") or "") for d in docs[:5])[:8000]
    state["citations"] = [
        {
            "source_id": d.get("source_id", ""),
            "date": d.get("date", ""),
            "url": d.get("url", ""),
            "title": d.get("title", ""),
            "chunk_id": d.get("chunk_id", ""),
        }
        for d in docs[:5]
    ]
    return state
