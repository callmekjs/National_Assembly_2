"""
Step-back Prompting
구체 질문 → LLM이 더 추상적인 상위 질문으로 변환 → 두 결과 RRF 합산.
예: "통일부 장관 발언?" → "외교통일위 현안 논의 내용?"
커버리지를 넓혀 특정 키워드에 치우친 검색을 보완한다.
"""
from __future__ import annotations

_SYSTEM_PROMPT = """너는 국회 회의록 검색 전문가야.
주어진 구체적인 질문을 더 넓고 추상적인 관련 질문으로 변환해줘.
예시:
- "통일부 장관 관련 주요 질의는?" → "외교통일위원회에서 다룬 주요 현안은?"
- "한미동맹 관련 발언은?" → "한반도 안보 정책에 관한 논의는?"
- "대북정책 핵심 쟁점은?" → "외교안보 정책 방향에 대한 위원들의 입장은?"
변환된 질문 하나만 출력하고 설명은 하지 마."""


def generate_step_back_query(query: str) -> str | None:
    """구체 질문 → 추상 질문 생성. 실패 시 None 반환."""
    try:
        from service.llm.llm_client import chat
        result = chat(_SYSTEM_PROMPT, query, max_tokens=100)
        if result and result.strip() and result.strip() != query:
            return result.strip()
    except Exception as e:
        print(f"[step_back] 상위 질문 생성 실패 ({e})")
    return None


def step_back_search(
    retriever,
    query: str,
    top_k: int = 5,
    **search_kwargs,
) -> list[dict]:
    """
    원본 질문 + 추상 질문으로 각각 검색 후 RRF 합산.
    """
    from service.rag.retrieval.multi_query import rrf_merge

    abstract_query = generate_step_back_query(query)
    if abstract_query:
        print(f"[step_back] 원본: {query}")
        print(f"[step_back] 추상: {abstract_query}")
    else:
        print("[step_back] 상위 질문 생성 실패 — 원본만 사용")
        return retriever.search(query, top_k=top_k, **search_kwargs)

    candidate_k = max(top_k * 3, 15)
    original_results = retriever.search(query, top_k=candidate_k, **search_kwargs)
    abstract_results = retriever.search(abstract_query, top_k=candidate_k, **search_kwargs)

    merged = rrf_merge([original_results, abstract_results])
    return merged[:top_k]
