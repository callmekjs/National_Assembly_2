from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"
MAX_LOAD = 3000
sep = "=" * 65

_PHASE_ORDER = ["opening", "presentation", "qa", "procedural", "closing", "unknown"]


def load_chunks(n: int = MAX_LOAD) -> list[dict]:
    if not CHUNKS_FILE.exists():
        print(f"[meeting_timeline_eval] chunks file not found: {CHUNKS_FILE}")
        return []
    chunks = []
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
            if len(chunks) >= n:
                break
    return chunks


def phase_distribution(chunks: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {p: 0 for p in _PHASE_ORDER}
    for c in chunks:
        phase = (c.get("metadata") or {}).get("meeting_phase", "unknown") or "unknown"
        dist[phase] = dist.get(phase, 0) + 1
    return dist


def chronological_sort_demo(chunks: list[dict]) -> None:
    from service.rag.retrieval.retriever import _apply_chronological_sort, _parse_turn_index

    by_date: dict[str, list[dict]] = {}
    for c in chunks:
        date = (c.get("metadata") or {}).get("meeting_date", "") or ""
        if date:
            by_date.setdefault(date, []).append(c)

    if len(by_date) < 2:
        print("  (다른 날짜의 청크 없음 — 시연 불가)")
        return

    dates = sorted(by_date.keys(), reverse=True)[:2]
    sample: list[dict] = []
    for d in dates:
        sample.extend(by_date[d][:3])

    import random
    random.shuffle(sample)
    for i, c in enumerate(sample):
        c["hybrid_score"] = round(0.9 - i * 0.1, 2)

    def _to_hit(c: dict) -> dict:
        return {
            "chunk_id": c.get("chunk_id", ""),
            "source_id": c.get("source_id", ""),
            "content": c.get("clean_text") or c.get("content") or "",
            "hybrid_score": c.get("hybrid_score", 0.5),
            "metadata": c.get("metadata", {}),
        }

    hits = [_to_hit(c) for c in sample]
    sorted_hits = _apply_chronological_sort(hits, question_type="comparison")

    print("정렬 전 (hybrid_score 순):")
    for h in hits[:4]:
        date = (h.get("metadata") or {}).get("meeting_date", "날짜없음")
        tidx = _parse_turn_index(str(h.get("chunk_id") or "")) or 0
        print(f"  [{date}] turn={tidx:4d}  score={h['hybrid_score']:.2f}  {h['content'][:60]}...")

    print()
    print("정렬 후 (시계열 오름차순):")
    for h in sorted_hits[:4]:
        date = (h.get("metadata") or {}).get("meeting_date", "날짜없음")
        tidx = _parse_turn_index(str(h.get("chunk_id") or "")) or 0
        print(f"  [{date}] turn={tidx:4d}  score={h['hybrid_score']:.2f}  {h['content'][:60]}...")


def main() -> None:
    chunks = load_chunks()
    print(f"[meeting_timeline_eval] loaded {len(chunks)} chunks")
    print()

    print(sep)
    print("=== 회의 국면(meeting_phase) 분포 ===")
    dist = phase_distribution(chunks)
    total = sum(dist.values())
    for phase in _PHASE_ORDER:
        cnt = dist.get(phase, 0)
        pct = cnt / max(total, 1)
        bar = "#" * min(int(pct * 40), 40)
        print(f"  {phase:<15}  {cnt:5d}  ({pct:.1%})  {bar}")
    print(f"  (총 {total}개 청크)")
    print()

    print(sep)
    print("=== 시계열 정렬 시뮬레이션 (comparison 질문 유형) ===")
    chronological_sort_demo(chunks)
    print()


if __name__ == "__main__":
    main()
