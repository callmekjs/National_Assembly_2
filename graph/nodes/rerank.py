from __future__ import annotations

import logging

from graph.state import QAState

logger = logging.getLogger(__name__)


def _sort_score(doc: dict) -> float:
    """우선순위: final_rerank_score > rerank_score > similarity (RRF).
    neural reranker / ensemble reranker가 붙인 점수를 우선 사용해
    Lost-in-the-middle을 줄인다.
    """
    for key in ("final_rerank_score", "rerank_score", "similarity"):
        val = doc.get(key)
        if val is not None:
            return float(val)
    return 0.0


def run(state: QAState) -> QAState:
    docs = state.get("retrieved", [])
    state["reranked"] = sorted(docs, key=_sort_score, reverse=True)

    if docs:
        sample = docs[0]
        score_key = next(
            (k for k in ("final_rerank_score", "rerank_score", "similarity") if k in sample),
            "similarity",
        )
        logger.info("[Rerank] sorted %d docs by %s", len(docs), score_key)

    return state
