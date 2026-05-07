from __future__ import annotations

from graph.state import QAState

DISCLAIMER = "\n\n※ 본 답변은 회의록 기반 정보 정리 결과입니다."


def run(state: QAState) -> QAState:
    answer = (state.get("draft_answer") or "").strip()
    if answer and DISCLAIMER not in answer:
        state["draft_answer"] = answer + DISCLAIMER
    return state
