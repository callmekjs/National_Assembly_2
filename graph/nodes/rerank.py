from __future__ import annotations

import logging
import re

from graph.state import QAState

logger = logging.getLogger(__name__)

_RERANK_ALPHA = 0.85  # hybrid_score 가중치 (lexical re-boost: 1 - _RERANK_ALPHA)


def _token_overlap(query: str, text: str) -> float:
    """질의 토큰이 문서에 몇 개나 등장하는지 비율 반환 (0~1)."""
    q_tokens = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", (query or "").lower()))
    t_tokens = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", (text or "").lower()))
    if not q_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def _rerank_score(doc: dict, query: str) -> float:
    """retriever 점수(hybrid_score / similarity) + 간단한 lexical re-boost를 합산."""
    base = 0.0
    for key in ("hybrid_score", "final_rerank_score", "rerank_score", "similarity"):
        val = doc.get(key)
        if val is not None:
            base = float(val)
            break
    text = doc.get("chunk_text") or doc.get("content") or ""
    lexical = _token_overlap(query, text)
    return _RERANK_ALPHA * base + (1.0 - _RERANK_ALPHA) * lexical


def run(state: QAState) -> QAState:
    docs = state.get("retrieved", [])
    if not docs:
        state["reranked"] = []
        return state

    query = state.get("rewritten_query") or state.get("question", "")
    scored = [(doc, _rerank_score(doc, query)) for doc in docs]
    scored.sort(key=lambda x: -x[1])

    reranked = []
    for doc, score in scored:
        d = dict(doc)
        d["rerank_score"] = round(score, 6)
        reranked.append(d)

    state["reranked"] = reranked

    if docs:
        logger.info(
            "[Rerank] %d docs → top score=%.4f (query=%s…)",
            len(docs),
            scored[0][1] if scored else 0.0,
            query[:30],
        )

    return state
