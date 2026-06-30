"""
Recall@K 간이 평가 — 실시간 검색 품질 모니터링

Ground-truth 없이도 동작하는 휴리스틱 지표:
  - keyword_hit_rate@k : 질문 키워드가 top-k 청크에 하나라도 포함되는 비율
  - score_gap            : top-1 vs top-k 평균 점수 차 (집중도)
  - diversity            : unique speaker 비율 (다양성)
  - avg_similarity       : top-k 평균 벡터 유사도
"""
from __future__ import annotations

import re


def _keywords(query: str) -> list[str]:
    tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", query)
    return [t for t in tokens if len(t) >= 2]


def evaluate(
    query: str,
    results: list[dict],
    k: int = 3,
) -> dict:
    """
    results: retriever.search()가 반환한 문서 리스트 (content/chunk_text 키 포함)
    k      : recall 계산 대상 상위 문서 수
    """
    if not results:
        return {"k": k, "total": 0}

    top = results[:k]
    keywords = _keywords(query)

    # keyword_hit_rate: top-k 중 질문 키워드 하나 이상 포함 문서 비율
    hit = 0
    for doc in top:
        text = (doc.get("content") or doc.get("chunk_text") or "").lower()
        if any(kw.lower() in text for kw in keywords):
            hit += 1
    khr = hit / len(top) if top else 0.0

    # score_gap: top-1 점수 - top-k 평균 점수
    score_key = "normalized_score" if "normalized_score" in results[0] else \
                "hybrid_score" if "hybrid_score" in results[0] else "similarity"
    scores = [float(d.get(score_key) or 0.0) for d in top]
    top1_score = scores[0] if scores else 0.0
    avg_score = sum(scores) / len(scores) if scores else 0.0
    score_gap = top1_score - avg_score

    # diversity: unique speaker / k
    # speaker는 최상위 키 또는 metadata 안에 있을 수 있음
    speakers = set()
    for doc in top:
        sp = (
            str(doc.get("speaker") or "").strip()
            or str((doc.get("metadata") or {}).get("speaker", "")).strip()
        )
        if sp:
            speakers.add(sp)
    diversity = len(speakers) / len(top) if top else 0.0

    # avg_similarity
    sims = [float(d.get("similarity") or 0.0) for d in top]
    avg_sim = sum(sims) / len(sims) if sims else 0.0

    return {
        "k": k,
        "total": len(results),
        "keyword_hit_rate": round(khr, 3),
        "score_gap": round(score_gap, 4),
        "diversity": round(diversity, 3),
        "avg_similarity": round(avg_sim, 4),
        "score_key_used": score_key,
    }


def print_eval(query: str, results: list[dict], k: int = 3, label: str = "") -> dict:
    m = evaluate(query, results, k)
    tag = f"[{label}] " if label else ""
    print(
        f"{tag}recall@{k} | "
        f"kw_hit={m['keyword_hit_rate']:.2f}  "
        f"div={m['diversity']:.2f}  "
        f"avg_sim={m['avg_similarity']:.4f}  "
        f"score_gap={m['score_gap']:.4f}  "
        f"(총 {m['total']}건)"
    )
    return m
