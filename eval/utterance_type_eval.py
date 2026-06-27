"""
발화유형 분류 정확도 개선 Before/After 평가

사용법:
    python eval/utterance_type_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import infer_utterance_type_with_confidence


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


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    print(f"utterance 청크: {len(chunks):,}개\n")

    old_dist: Counter = Counter()
    new_dist: Counter = Counter()
    changed: list[dict] = []
    conf_buckets: Counter = Counter()
    low_conf_questions = 0

    for c in chunks:
        meta = c.get("metadata", {})
        old_type = meta.get("utterance_type", "statement")
        speaker_role = c.get("speaker_role", "")
        position_type = str(meta.get("position_type") or "")
        text = c.get("clean_text", "")

        new_type, conf = infer_utterance_type_with_confidence(text, speaker_role, position_type)

        old_dist[old_type] += 1
        new_dist[new_type] += 1

        if new_type != old_type:
            changed.append({
                "chunk_id": c.get("chunk_id", ""),
                "old": old_type,
                "new": new_type,
                "conf": conf,
                "text_preview": text[:80],
            })

        bucket = f"{int(conf * 10) * 10}-{int(conf * 10) * 10 + 10}%"
        conf_buckets[bucket] += 1

        if new_type == "question" and conf < 0.5:
            low_conf_questions += 1

    sep = "=" * 65
    thin = "-" * 65

    print(sep)
    print("  발화유형 분류 Before / After 비교")
    print(sep)

    print(f"\n{'유형':<12} {'Before':>10} {'After':>10} {'변화':>10}")
    print(thin)
    for utype in ["question", "answer", "statement", "procedural"]:
        b = old_dist.get(utype, 0)
        a = new_dist.get(utype, 0)
        delta = a - b
        delta_str = f"+{delta:,}" if delta > 0 else (f"{delta:,}" if delta < 0 else "—")
        print(f"{utype:<12} {b:>10,} {a:>10,} {delta_str:>10}")
    print(thin)
    print(f"{'합계':<12} {sum(old_dist.values()):>10,} {sum(new_dist.values()):>10,}")

    print(f"\n{sep}")
    print("  변경 케이스 분석")
    print(sep)
    change_types: Counter = Counter()
    for item in changed:
        change_types[f"{item['old']} → {item['new']}"] += 1
    for change_label, cnt in change_types.most_common():
        print(f"  {change_label:<25} {cnt:>6,}건")

    if changed:
        print(f"\n  상위 10개 변경 예시 (question → statement):")
        examples = [c for c in changed if c["old"] == "question" and c["new"] == "statement"][:10]
        for ex in examples:
            print(f"  [{ex['conf']:.2f}] {ex['text_preview']}...")

    print(f"\n{sep}")
    print("  신뢰도 분포 (새 분류 기준)")
    print(sep)
    for bucket in sorted(conf_buckets.keys()):
        cnt = conf_buckets[bucket]
        bar = "█" * min(40, cnt // max(1, len(chunks) // 400))
        print(f"  {bucket:<10} {cnt:>7,}개  {bar}")

    print(f"\n{sep}")
    print("  QA 쌍 영향 추정 (confidence < 0.5 필터 기준)")
    print(sep)
    new_questions = new_dist.get("question", 0)
    print(f"  새 question 청크 수:            {new_questions:>7,}개")
    print(f"  confidence < 0.5 제외 예상:     {low_conf_questions:>7,}개")
    remaining = new_questions - low_conf_questions
    print(f"  QA pairing 대상 question:       {remaining:>7,}개")
    if new_questions:
        print(f"  필터율:                         {low_conf_questions/new_questions*100:>7.1f}%")

    print(sep)


if __name__ == "__main__":
    main()
