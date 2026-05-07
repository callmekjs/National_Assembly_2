from __future__ import annotations

from graph.state import QAState


def run(state: QAState) -> QAState:
    question = (state.get("question") or "").strip()
    state["rewritten_query"] = question
    return state
