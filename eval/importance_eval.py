"""
발언 중요도 점수화 알고리즘 Before/After 평가

사용법:
    python eval/importance_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import infer_importance_score
from service.rag.retrieval.retriever import _apply_importance_boost, _IMPORTANCE_BOOST


def load_utterance_chunks() -> list[dict]:
    chunks = []
    if not CHUNKS_FILE.exists():
        print(f"청크 파일 없음: {CHUNKS_FILE}")
        return chunks
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            if c.get("metadata", {}).get("chunk_type", "utterance") == "utterance":
                chunks.append(c)
    return chunks


def simulate_boost(chunks: list[dict], query_keywords: list[str], top_k: int = 8) -> tuple[list[dict], list[dict]]:
    filtered = [c for c in chunks if any(kw in (c.get("clean_text") or "") for kw in query_keywords)]
    if not filtered:
        return [], []
    for c in filtered:
        c["hybrid_score"] = float(len([kw for kw in query_keywords if kw in (c.get("clean_text") or "")])) / len(query_keywords)
    before = sorted(filtered, key=lambda x: -x.get("hybrid_score", 0.0))[:top_k]
    hits_for_boost = [
        {
            "hybrid_score": c["hybrid_score"],
            "metadata": c.get("metadata", {}),
            "clean_text": c.get("clean_text", ""),
            "speaker": c.get("speaker", ""),
        }
        for c in filtered
    ]
    after_hits = _apply_importance_boost(hits_for_boost, question_type="topic_search")[:top_k]
    return before, after_hits


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    if not chunks:
        return
    print(f"utterance 청크: {len(chunks):,}개\n")

    scored = []
    position_scores: dict[str, list[float]] = defaultdict(list)
    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("clean_text", "")
        utype = meta.get("utterance_type", "statement")
        ptype = meta.get("position_type", "기타")
        score = infer_importance_score(text, utterance_type=utype, position_type=ptype)
        scored.append((score, c.get("speaker", ""), text, ptype))
        position_scores[ptype].append(score)

    sep = "=" * 65

    print(sep)
    print("  importance_score 분포")
    print(sep)
    buckets = Counter()
    for score, _, _, _ in scored:
        if score == 0.0:
            buckets["0.00 (없음)"] += 1
        elif score < 0.20:
            buckets["0.01–0.19 (미약)"] += 1
        elif score < 0.45:
            buckets["0.20–0.44 (보통)"] += 1
        elif score < 0.75:
            buckets["0.45–0.74 (강함)"] += 1
        else:
            buckets["0.75+ (매우 강함)"] += 1

    for label in ["0.00 (없음)", "0.01–0.19 (미약)", "0.20–0.44 (보통)", "0.45–0.74 (강함)", "0.75+ (매우 강함)"]:
        cnt = buckets.get(label, 0)
        pct = cnt / len(scored) * 100
        bar = "█" * min(30, int(pct / 2))
        print(f"  {label:<22} {cnt:>7,}개 ({pct:4.1f}%) {bar}")

    print(f"\n{sep}")
    print("  position_type별 평균 중요도")
    print(sep)
    for ptype in ["정부측", "의원", "위원장", "후보자", "전문위원", "기타"]:
        scores = position_scores.get(ptype, [])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        bar = "█" * min(20, int(avg * 20))
        print(f"  {ptype:<8} n={len(scores):>6,}  avg={avg:.3f}  {bar}")

    print(f"\n{sep}")
    print("  상위 10개 중요도 청크")
    print(sep)
    top10 = sorted(scored, key=lambda x: -x[0])[:10]
    for score, speaker, text, ptype in top10:
        print(f"  [{score:.2f}] {ptype:<6} {speaker[:6]:<6} {text[:65]}...")

    print(f"\n{sep}")
    print(f"  부스트 시뮬레이션 (max boost: {_IMPORTANCE_BOOST} × importance_score)")
    print(sep)

    test_queries = [
        (["추진", "하겠습니다"], "정부 추진 약속"),
        (["정부", "입장"], "정부 입장 발언"),
        (["시행령", "예산안"], "정책 결정 발언"),
        (["재외국민", "보호"], "외교 현안 질의"),
        (["방송", "독립"], "방송 정책 논의"),
    ]

    for keywords, label in test_queries:
        before, after = simulate_boost(chunks, keywords)
        if not before:
            print(f"\n  [{label}] 해당 청크 없음")
            continue
        b_avg = sum(float((c.get("metadata") or {}).get("importance_score", 0.0)) for c in before) / max(len(before), 1)
        a_avg = sum(float((x.get("metadata") or {}).get("importance_score", 0.0)) for x in after) / max(len(after), 1)
        print(f"\n  [{label}] top-{len(before)} avg importance_score: Before={b_avg:.2f} → After={a_avg:.2f}")

    print(sep)


if __name__ == "__main__":
    main()
