"""
핵심 쟁점 추출 알고리즘 Before/After 평가

사용법:
    python eval/issue_extract_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

sys.path.insert(0, str(ROOT))

from service.rag.query.question_types import infer_issue_score
from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST


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
    hits_for_boost = [{"hybrid_score": c["hybrid_score"], "metadata": c.get("metadata", {}), "clean_text": c.get("clean_text", ""), "speaker": c.get("speaker", "")} for c in filtered]
    after_hits = _apply_issue_boost(hits_for_boost, question_type="issue_extract")[:top_k]
    return before, after_hits


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    if not chunks:
        return
    print(f"utterance 청크: {len(chunks):,}개\n")

    scored = []
    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("clean_text", "")
        utype = meta.get("utterance_type", "statement")
        ptype = meta.get("position_type", "")
        score = infer_issue_score(text, utterance_type=utype, position_type=ptype)
        scored.append((score, c.get("speaker", ""), text))

    sep = "=" * 65
    thin = "-" * 65

    print(sep)
    print("  issue_score 분포")
    print(sep)
    buckets = Counter()
    for score, _, _ in scored:
        if score == 0.0:
            buckets["0.00 (없음)"] += 1
        elif score < 0.25:
            buckets["0.01–0.24 (미약)"] += 1
        elif score < 0.50:
            buckets["0.25–0.49 (보통)"] += 1
        elif score < 0.75:
            buckets["0.50–0.74 (강함)"] += 1
        else:
            buckets["0.75+ (매우 강함)"] += 1

    for label in ["0.00 (없음)", "0.01–0.24 (미약)", "0.25–0.49 (보통)", "0.50–0.74 (강함)", "0.75+ (매우 강함)"]:
        cnt = buckets.get(label, 0)
        pct = cnt / len(scored) * 100
        bar = "█" * min(30, int(pct / 2))
        print(f"  {label:<22} {cnt:>7,}개 ({pct:4.1f}%) {bar}")

    print(f"\n{sep}")
    print("  상위 10개 쟁점 청크")
    print(sep)
    top10 = sorted(scored, key=lambda x: -x[0])[:10]
    for score, speaker, text in top10:
        print(f"  [{score:.2f}] {speaker[:8]:<8} {text[:70]}...")

    print(f"\n{sep}")
    print(f"  부스트 시뮬레이션 (max boost: {_ISSUE_SCORE_BOOST} × issue_score)")
    print(sep)

    test_queries = [
        (["예산", "낭비"], "예산 낭비 쟁점"),
        (["비리", "위반"], "비리·위반 쟁점"),
        (["우려", "문제"], "우려·문제 발언"),
        (["대북제재", "완화"], "대북제재 완화"),
        (["방송", "독립"], "방송 독립 쟁점"),
    ]

    for keywords, label in test_queries:
        before, after = simulate_boost(chunks, keywords)
        if not before:
            print(f"\n  [{label}] 해당 청크 없음")
            continue
        b_avg_score = sum(float((x.get("metadata") or {}).get("issue_score", 0.0)) for x in [{"metadata": c.get("metadata", {})} for c in before]) / max(len(before), 1)
        a_avg_score = sum(float((x.get("metadata") or {}).get("issue_score", 0.0)) for x in after) / max(len(after), 1)
        print(f"\n  [{label}] top-{len(before)} avg issue_score: Before={b_avg_score:.2f} → After={a_avg_score:.2f}")

    print(sep)


if __name__ == "__main__":
    main()
