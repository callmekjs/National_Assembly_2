"""
MMR (Maximal Marginal Relevance) 다양성 재정렬

λ * sim(doc, query) - (1-λ) * max_sim(doc, already_selected)

λ → 1 : 순수 관련도 우선
λ → 0 : 순수 다양성 우선
기본 λ=0.7 : 관련도 70 % + 다양성 30 %
"""
from __future__ import annotations

import math


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def mmr_rerank(
    query_vec: list[float],
    candidates: list[dict],
    top_k: int | None = None,
    lambda_: float = 0.7,
    embedding_key: str = "embedding",
) -> list[dict]:
    """
    임베딩 벡터 기반 MMR 재정렬.

    candidates 각 항목에 embedding_key 필드가 있어야 한다.
    embedding이 없는 문서는 관련도 점수(similarity/hybrid_score)만으로 선택한다.
    """
    if not candidates:
        return candidates

    k = top_k if top_k else len(candidates)

    # embedding이 있는 문서와 없는 문서 분리
    with_emb = [(i, d) for i, d in enumerate(candidates) if d.get(embedding_key)]
    without_emb = [(i, d) for i, d in enumerate(candidates) if not d.get(embedding_key)]

    selected: list[dict] = []
    remaining: list[tuple[int, dict]] = list(with_emb)

    while remaining and len(selected) < k:
        best_score = -float("inf")
        best_idx = 0

        for j, (orig_i, doc) in enumerate(remaining):
            emb = doc[embedding_key]
            rel = _cosine(query_vec, emb)

            if not selected:
                # 선택된 것이 없으면 순수 관련도
                max_sim_sel = 0.0
            else:
                max_sim_sel = max(
                    _cosine(emb, s[embedding_key])
                    for s in selected
                    if s.get(embedding_key)
                ) if any(s.get(embedding_key) for s in selected) else 0.0

            mmr_score = lambda_ * rel - (1 - lambda_) * max_sim_sel
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = j

        chosen_orig_i, chosen_doc = remaining.pop(best_idx)
        d = dict(chosen_doc)
        d["mmr_score"] = best_score
        selected.append(d)

    # embedding 없는 문서는 원본 점수 순 유지
    for _, doc in without_emb:
        if len(selected) >= k:
            break
        selected.append(doc)

    return selected[:k]
