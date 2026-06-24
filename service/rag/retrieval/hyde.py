"""
HyDE (Hypothetical Document Embedding)
질문 → LLM이 가상 답변(문서) 생성 → 그 답변을 임베딩으로 변환해 검색
질문과 실제 문서 사이의 표현 격차를 줄여 recall을 높인다.
"""
from __future__ import annotations


_SYSTEM_PROMPT = """너는 국회 회의록 전문가야.
주어진 질문에 대해 실제 국회 회의록에서 발췌한 것처럼 가상의 답변 문단을 작성해줘.
발언자 이름, 구체적인 정책 용어, 날짜 등을 포함해 현실적으로 작성해.
답변만 출력하고 설명은 하지 마."""


def generate_hypothetical_doc(query: str) -> str | None:
    """질문에 대한 가상 답변 생성. 실패 시 None 반환."""
    try:
        from service.llm.llm_client import chat
        hyp_doc = chat(_SYSTEM_PROMPT, query, max_tokens=300)
        if hyp_doc and len(hyp_doc.strip()) > 20:
            return hyp_doc.strip()
    except Exception as e:
        print(f"[hyde] 가상 답변 생성 실패 ({e})")
    return None


def hyde_search(
    retriever,
    query: str,
    top_k: int = 5,
    **search_kwargs,
) -> list[dict]:
    """
    HyDE 검색:
    1) 원본 질문으로 가상 답변 생성
    2) 가상 답변을 임베딩해서 검색
    3) 실패 시 원본 질문으로 폴백
    """
    hyp_doc = generate_hypothetical_doc(query)
    if hyp_doc:
        print(f"[hyde] 가상 답변 생성 완료 ({len(hyp_doc)}자)")
        print(f"  → {hyp_doc[:80]}...")
        # 가상 답변으로 검색 (query 자리에 hyp_doc을 넣어 임베딩)
        return _search_with_text(retriever, query, hyp_doc, top_k, **search_kwargs)
    else:
        print("[hyde] 생성 실패 — 원본 질문으로 폴백")
        return retriever.search(query, top_k=top_k, **search_kwargs)


def _search_with_text(retriever, original_query: str, embed_text: str, top_k: int, **kwargs) -> list[dict]:
    """embed_text를 임베딩해서 검색하되, 재랭킹은 original_query 기준으로 수행."""
    from service.rag.retrieval.date_range import normalize_meeting_date_range

    vector = retriever.encoder.encode_query(embed_text)

    date_from = kwargs.get("date_from")
    date_to = kwargs.get("date_to")
    df, dt = normalize_meeting_date_range(
        str(date_from) if date_from else None,
        str(date_to) if date_to else None,
    )
    committee = kwargs.get("committee")
    filters = {
        "committee": committee or "",
        "date_from": df or "",
        "date_to": dt or "",
        "require_speaker": bool(kwargs.get("require_speaker", False)),
    }

    candidate_multiplier = int(kwargs.get("candidate_multiplier", 50))
    candidate_k = max(top_k, top_k * candidate_multiplier)
    include_metadata = kwargs.get("include_metadata", True)
    min_similarity = float(kwargs.get("min_similarity", 0.0))
    alpha = float(kwargs.get("alpha", 0.8))

    rows = retriever.store.search_similar(vector, top_k=candidate_k, filters=filters)

    out = []
    for row in rows:
        if row.similarity < min_similarity:
            continue
        lexical_score = retriever._lexical_overlap_score(original_query, row.content)
        keyword_boost = retriever._domain_keyword_boost(original_query, row.content)
        keyword_boost += retriever._phrase_match_boost(original_query, row.content)
        hybrid_score = alpha * float(row.similarity) + (1 - alpha) * lexical_score + keyword_boost
        out.append({
            "content": row.content,
            "chunk_id": row.chunk_id,
            "source_id": row.source_id,
            "date": row.metadata.get("meeting_date", ""),
            "title": row.metadata.get("section", ""),
            "url": row.metadata.get("url", ""),
            "similarity": row.similarity,
            "lexical_score": lexical_score,
            "keyword_boost": keyword_boost,
            "hybrid_score": hybrid_score,
            "speaker": row.metadata.get("speaker", ""),
            "speaker_role": row.metadata.get("speaker_role", ""),
            "metadata": row.metadata if include_metadata else {},
        })

    out = sorted(
        out,
        key=lambda x: (
            -float(x.get("hybrid_score", 0.0) or 0.0),
            str(x.get("chunk_id") or x.get("source_id") or ""),
        ),
    )
    out = retriever._dedupe_by_chunk_id(out)

    use_reranker = kwargs.get("use_reranker", False)
    if use_reranker and out:
        from service.rag.retrieval.reranker import create_default_reranker
        reranker = create_default_reranker()
        out = reranker.rerank(original_query, out, top_k=top_k)
    elif kwargs.get("balance_speakers", False) and out:
        out = retriever._balance_speakers(out, top_k)
    else:
        out = out[:top_k]

    return out
