"""
Multi-reranker Ensemble (Neural + LLM → RRF)

Neural Reranker와 LLM Reranker를 각각 독립 실행한 뒤
두 순위 목록을 RRF(Reciprocal Rank Fusion)로 합산해 최종 순위를 결정한다.

단독 재정렬보다 안정적: 한 쪽이 실패해도 나머지로 폴백.
"""
from __future__ import annotations


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def ensemble_rerank(
    query: str,
    candidates: list[dict],
    top_k: int | None = None,
    neural_weight: float = 0.5,
    llm_weight: float = 0.5,
) -> list[dict]:
    """
    Neural + LLM 두 재정렬기를 돌리고 RRF 점수로 합산한다.
    한 쪽이 실패하면 성공한 쪽 결과만 사용한다.
    """
    if not candidates:
        return candidates

    neural_order: list[dict] | None = None
    llm_order: list[dict] | None = None

    try:
        from service.rag.retrieval.reranker import create_neural_reranker
        neural_order = create_neural_reranker().rerank(query, candidates)
        print(f"[ensemble_reranker] Neural Reranker 완료 ({len(neural_order)}개)")
    except Exception as e:
        print(f"[ensemble_reranker] Neural Reranker 실패: {e}")

    try:
        from service.rag.retrieval.llm_reranker import llm_rerank
        llm_order = llm_rerank(query, candidates)
        print(f"[ensemble_reranker] LLM Reranker 완료 ({len(llm_order)}개)")
    except Exception as e:
        print(f"[ensemble_reranker] LLM Reranker 실패: {e}")

    # 둘 다 실패 → 원본 반환
    if neural_order is None and llm_order is None:
        print("[ensemble_reranker] 두 재정렬기 모두 실패, 원본 반환")
        return candidates[:top_k] if top_k else candidates

    # chunk_id → RRF 누적
    scores: dict[str, float] = {}
    id_to_doc: dict[str, dict] = {}

    def _key(d: dict) -> str:
        return str(d.get("chunk_id") or d.get("source_id") or id(d))

    if neural_order is not None:
        for rank, doc in enumerate(neural_order, 1):
            k = _key(doc)
            scores[k] = scores.get(k, 0.0) + neural_weight * _rrf_score(rank)
            if k not in id_to_doc:
                id_to_doc[k] = doc

    if llm_order is not None:
        for rank, doc in enumerate(llm_order, 1):
            k = _key(doc)
            scores[k] = scores.get(k, 0.0) + llm_weight * _rrf_score(rank)
            if k not in id_to_doc:
                id_to_doc[k] = doc

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    result = []
    for k, score in ranked:
        d = dict(id_to_doc[k])
        d["ensemble_score"] = score
        result.append(d)

    return result[:top_k] if top_k else result
