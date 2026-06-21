"""
LLM Reranker
GPT-4o-mini에게 후보 청크 목록을 주고 관련도 순서로 나열하게 요청.
모델 다운로드 없이 API 호출만으로 도메인 특화 판단 가능.
"""
from __future__ import annotations

import json
import re


_SYSTEM_PROMPT = """너는 국회 회의록 검색 전문가야.
주어진 질문과 후보 문서 목록을 보고, 질문과 가장 관련 있는 순서대로 문서 번호를 JSON 배열로 반환해.
예: [3, 1, 5, 2, 4]
관련 없는 문서는 제외해도 됨. 배열만 출력하고 설명은 하지 마."""


def llm_rerank(
    query: str,
    candidates: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    """
    LLM에게 순위 결정을 요청한다.
    candidates 수가 많으면 토큰이 많이 쓰이므로 상위 10개로 제한.
    """
    if not candidates:
        return candidates

    # LLM에 넘길 후보 최대 10개
    pool = candidates[:10]

    # 후보 목록 텍스트 구성
    doc_list = "\n".join(
        f"[{i+1}] {d.get('content', '')[:200]}"
        for i, d in enumerate(pool)
    )
    user_msg = f"질문: {query}\n\n후보 문서:\n{doc_list}"

    try:
        from service.llm.llm_client import chat
        raw = chat(_SYSTEM_PROMPT, user_msg, max_tokens=100)

        # JSON 배열 파싱
        m = re.search(r"\[[\d,\s]+\]", raw)
        if m:
            order = json.loads(m.group())
            reranked = []
            seen = set()
            for idx in order:
                i = int(idx) - 1
                if 0 <= i < len(pool) and i not in seen:
                    doc = dict(pool[i])
                    doc["llm_rank"] = len(reranked) + 1
                    reranked.append(doc)
                    seen.add(i)
            # LLM이 빠뜨린 나머지 후보 뒤에 붙이기
            for i, d in enumerate(pool):
                if i not in seen:
                    reranked.append(d)

            print(f"[llm_reranker] LLM 순위 결정 완료 ({len(reranked)}개)")
            return reranked[:top_k] if top_k else reranked

    except Exception as e:
        print(f"[llm_reranker] 실패 ({e}), 원본 순서 반환")

    return candidates[:top_k] if top_k else candidates
