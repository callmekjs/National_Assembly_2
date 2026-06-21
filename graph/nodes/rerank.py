from __future__ import annotations

from graph.state import QAState


def run(state: QAState) -> QAState:
    docs = state.get("retrieved", [])
    state["reranked"] = sorted(docs, key=lambda x: x.get("similarity", 0.0), reverse=True)
    return state
