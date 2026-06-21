"""
Multi-query Retrieval
질문 1개 → LLM으로 변형 질문 3개 생성 → 각각 검색 → RRF로 통합
"""
from __future__ import annotations

import json
import re

_RRF_K = 60  # RRF 표준 상수


def generate_queries(query: str, n: int = 3) -> list[str]:
    """LLM으로 변형 질문 n개 생성. 실패 시 원본만 반환."""
    try:
        from service.llm.llm_client import chat
        system = (
            "너는 정보 검색 전문가야. "
            "주어진 질문을 의미는 같지만 표현이 다른 질문으로 변환해. "
            f"정확히 {n}개를 JSON 배열로만 반환해. 예: [\"질문1\", \"질문2\", \"질문3\"]"
        )
        user = f"원본 질문: {query}"
        raw = chat(system, user, max_tokens=300)

        # JSON 배열 추출
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            variants = json.loads(m.group())
            if isinstance(variants, list) and variants:
                # 원본과 동일한 것 제거, n개로 제한
                result = [q for q in variants if isinstance(q, str) and q.strip() and q.strip() != query]
                return result[:n]
    except Exception as e:
        print(f"[multi_query] 변형 질문 생성 실패 ({e}), 원본만 사용")
    return []


def rrf_merge(ranked_lists: list[list[dict]], k: int = _RRF_K) -> list[dict]:
    """
    여러 검색 결과 리스트를 Reciprocal Rank Fusion으로 통합.
    score = sum(1 / (k + rank)) — chunk_id 기준으로 중복 합산.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    for result_list in ranked_lists:
        for rank, doc in enumerate(result_list, start=1):
            cid = str(doc.get("chunk_id") or doc.get("source_id", ""))
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in docs:
                docs[cid] = doc

    merged = sorted(docs.values(), key=lambda d: scores.get(
        str(d.get("chunk_id") or d.get("source_id", "")), 0.0
    ), reverse=True)

    # rrf_score를 각 doc에 기록
    for doc in merged:
        cid = str(doc.get("chunk_id") or doc.get("source_id", ""))
        doc["rrf_score"] = round(scores.get(cid, 0.0), 6)

    return merged


def multi_query_search(
    retriever,
    query: str,
    top_k: int = 5,
    n_variants: int = 3,
    **search_kwargs,
) -> list[dict]:
    """
    원본 질문 + 변형 질문으로 각각 검색 후 RRF 통합.
    retriever: Retriever 인스턴스
    search_kwargs: committee, date_from, date_to, alpha 등 기존 search() 파라미터
    """
    # 원본 검색 (더 넓은 후보 풀)
    candidate_k = max(top_k * 3, 15)
    original_results = retriever.search(query, top_k=candidate_k, **search_kwargs)

    # 변형 질문 생성
    variants = generate_queries(query, n=n_variants)
    print(f"[multi_query] 원본 + 변형 {len(variants)}개 = 총 {1 + len(variants)}회 검색")
    for i, v in enumerate(variants, 1):
        print(f"  [{i}] {v}")

    all_results = [original_results]
    for variant in variants:
        try:
            results = retriever.search(variant, top_k=candidate_k, **search_kwargs)
            all_results.append(results)
        except Exception as e:
            print(f"[multi_query] 변형 검색 실패: {e}")

    merged = rrf_merge(all_results)
    return merged[:top_k]
