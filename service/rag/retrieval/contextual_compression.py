"""
Contextual Compression
검색된 청크에서 질문과 무관한 부분을 LLM이 제거 후 핵심만 반환.
토큰 절감 + 노이즈 감소 → LLM 답변 정밀도 향상.
"""
from __future__ import annotations

_SYSTEM_PROMPT = """너는 텍스트 압축 전문가야.
주어진 '문서'에서 '질문'과 직접 관련 있는 문장만 남기고 나머지는 제거해줘.
- 관련 문장이 없으면 빈 문자열을 반환해.
- 원문 표현을 그대로 유지해 (요약하거나 바꾸지 마).
- 압축된 텍스트만 출력하고 설명은 하지 마."""


def compress_doc(query: str, content: str, max_tokens: int = 400) -> str:
    """질문과 관련 없는 부분 제거. 실패 시 원본 반환."""
    if not content or len(content) < 100:
        return content
    try:
        from service.llm.llm_client import chat
        user = f"질문: {query}\n\n문서:\n{content[:1500]}"
        compressed = chat(_SYSTEM_PROMPT, user, max_tokens=max_tokens)
        if compressed and len(compressed.strip()) > 20:
            return compressed.strip()
    except Exception as e:
        print(f"[compression] 압축 실패 ({e})")
    return content


def compress_docs(
    query: str,
    docs: list[dict],
    max_tokens_per_doc: int = 400,
    skip_short: int = 150,
) -> list[dict]:
    """
    docs 리스트 각각을 압축해 반환.
    skip_short 자 이하 청크는 이미 짧으므로 압축 생략.
    """
    compressed = []
    for doc in docs:
        content = doc.get("content", "")
        if len(content) <= skip_short:
            compressed.append(doc)
            continue

        new_content = compress_doc(query, content, max_tokens=max_tokens_per_doc)
        new_doc = dict(doc)
        if new_content and new_content != content:
            new_doc["content"] = new_content
            new_doc["_compressed"] = True
            new_doc["_original_len"] = len(content)
            print(f"[compression] {doc.get('chunk_id','')} {len(content)}자 → {len(new_content)}자")
        compressed.append(new_doc)

    return compressed
