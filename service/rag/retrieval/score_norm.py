"""
Score Normalization — min-max 정규화 후 가중 앙상블

여러 점수(벡터 유사도, 어휘 중복, 키워드 부스트)의 스케일이 달라
단순 가중합이 한 점수에 편향될 때, min-max 정규화로 0-1 범위를 맞춘 뒤 합산한다.
"""
from __future__ import annotations


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    span = hi - lo
    if span < 1e-9:
        return [0.0] * len(values)
    return [(v - lo) / span for v in values]


def normalize_scores(
    candidates: list[dict],
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """
    각 후보 문서의 점수 필드를 min-max 정규화해
    `normalized_score` 필드를 채우고 내림차순 정렬한 새 리스트를 반환한다.

    weights 예: {"similarity": 0.6, "lexical_score": 0.3, "keyword_boost": 0.1}
    """
    if not candidates:
        return candidates

    w = weights or {"similarity": 0.6, "lexical_score": 0.3, "keyword_boost": 0.1}
    score_keys = [k for k in w if k in candidates[0] or any(k in d for d in candidates)]

    # 각 키별 값 목록
    raw: dict[str, list[float]] = {}
    for key in score_keys:
        vals = [float(d.get(key) or 0.0) for d in candidates]
        raw[key] = vals

    # 정규화
    normed: dict[str, list[float]] = {k: _minmax(v) for k, v in raw.items()}

    result = []
    for i, doc in enumerate(candidates):
        d = dict(doc)
        score = sum(w.get(k, 0.0) * normed[k][i] for k in score_keys)
        d["normalized_score"] = score
        result.append(d)

    return sorted(
        result,
        key=lambda x: (
            -float(x.get("normalized_score", 0.0) or 0.0),
            str(x.get("chunk_id") or x.get("source_id") or ""),
        ),
    )
