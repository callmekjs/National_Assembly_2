"""
Fusion Retrieval (RRF)
벡터 검색 + 키워드(BM25-style) 검색 결과를 Reciprocal Rank Fusion으로 통합.
현재 alpha 하이브리드 점수보다 robust한 순위 통합.
"""
from __future__ import annotations

import re
from math import log

from service.rag.retrieval.multi_query import rrf_merge


def bm25_score(query: str, content: str, k1: float = 1.5, b: float = 0.75, avg_dl: int = 300) -> float:
    """경량 BM25 스코어 (IDF 생략, 단일 문서 기준)."""
    q_tokens = [t for t in re.findall(r"[가-힣a-zA-Z0-9]+", query.lower()) if len(t) >= 2]
    c_tokens = re.findall(r"[가-힣a-zA-Z0-9]+", content.lower())
    if not q_tokens or not c_tokens:
        return 0.0

    dl = len(c_tokens)
    tf_map: dict[str, int] = {}
    for t in c_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    score = 0.0
    for qt in q_tokens:
        tf = tf_map.get(qt, 0)
        if tf == 0:
            continue
        idf = log(2)  # 단일 문서라 IDF 상수 사용
        score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))

    return score


def fusion_search(
    retriever,
    query: str,
    top_k: int = 5,
    **search_kwargs,
) -> list[dict]:
    """
    1) 벡터 검색 (기존 방식) → 순위 리스트 A
    2) BM25 스코어로 재정렬 → 순위 리스트 B
    3) RRF로 A+B 통합
    """
    candidate_k = max(top_k * 5, 25)
    # 벡터 검색 — candidate pool 확보
    vector_results = retriever.search(query, top_k=candidate_k, **search_kwargs)

    if not vector_results:
        return []

    # BM25로 재정렬한 결과 리스트 생성
    bm25_ranked = sorted(
        vector_results,
        key=lambda d: (
            -bm25_score(query, d.get("content", "")),
            str(d.get("chunk_id") or d.get("source_id") or ""),
        ),
    )

    # RRF 통합
    merged = rrf_merge([vector_results, bm25_ranked])
    return merged[:top_k]
