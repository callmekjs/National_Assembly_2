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


def load_chunks(n: int = MAX_LOAD) -> list[dict]:
    if not CHUNKS_FILE.exists():
        print(f"[smart_merge_eval] chunks file not found: {CHUNKS_FILE}")
        return []
    chunks = []
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
            if len(chunks) >= n:
                break
    return chunks


def simulate_merge(chunks: list[dict], gap: int) -> dict:
    from service.rag.retrieval.retriever import _merge_adjacent_hits, _parse_turn_index

    # source_id 기준 그룹화
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id") or ""
        if sid:
            groups.setdefault(sid, []).append(c)

    total_pairs = 0
    mergeable_pairs = 0
    blocked_by_length = 0

    for sid, grp in groups.items():
        grp.sort(key=lambda x: _parse_turn_index(str(x.get("chunk_id") or "")) or 0)
        for i in range(len(grp) - 1):
            tidx_a = _parse_turn_index(str(grp[i].get("chunk_id") or ""))
            tidx_b = _parse_turn_index(str(grp[i + 1].get("chunk_id") or ""))
            if tidx_a is None or tidx_b is None:
                continue
            total_pairs += 1
            dist = tidx_b - tidx_a
            if dist <= gap:
                len_a = len(grp[i].get("clean_text") or grp[i].get("content") or "")
                len_b = len(grp[i + 1].get("clean_text") or grp[i + 1].get("content") or "")
                if len_a + len_b + 2 <= 1200:
                    mergeable_pairs += 1
                else:
                    blocked_by_length += 1

    return {
        "total_chunks": len(chunks),
        "total_consecutive_pairs": total_pairs,
        "mergeable_pairs": mergeable_pairs,
        "blocked_by_length": blocked_by_length,
        "merge_rate": mergeable_pairs / max(total_pairs, 1),
    }


def demo_merge(chunks: list[dict]) -> None:
    from service.rag.retrieval.retriever import _merge_adjacent_hits, _parse_turn_index

    # 같은 source_id에서 연속 turn을 가진 청크 쌍 찾기
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id") or ""
        if sid:
            groups.setdefault(sid, []).append(c)

    sample_hits: list[dict] = []
    for sid, grp in groups.items():
        grp.sort(key=lambda x: _parse_turn_index(str(x.get("chunk_id") or "")) or 0)
        for i in range(len(grp) - 1):
            tidx_a = _parse_turn_index(str(grp[i].get("chunk_id") or ""))
            tidx_b = _parse_turn_index(str(grp[i + 1].get("chunk_id") or ""))
            if tidx_a is None or tidx_b is None:
                continue
            if tidx_b - tidx_a <= 2:
                # 두 청크를 hit 형태로 변환
                def _to_hit(c: dict, score: float) -> dict:
                    return {
                        "chunk_id": c.get("chunk_id", ""),
                        "source_id": c.get("source_id", ""),
                        "content": c.get("clean_text") or c.get("content") or "",
                        "hybrid_score": score,
                        "speaker": c.get("speaker", ""),
                    }
                sample_hits = [_to_hit(grp[i], 0.9), _to_hit(grp[i + 1], 0.7)]
                break
        if sample_hits:
            break

    if not sample_hits:
        print("  (연속 청크 샘플 없음)")
        return

    print("병합 전:")
    for h in sample_hits:
        print(f"  [{h['chunk_id']}] score={h['hybrid_score']}")
        print(f"  {(h['content'])[:120]}...")
        print()

    merged = _merge_adjacent_hits(sample_hits)
    print("병합 후:")
    for h in merged:
        ids = h.get("_merged_chunk_ids", [h.get("chunk_id")])
        print(f"  [{' + '.join(ids)}] score={h['hybrid_score']:.2f}")
        print(f"  {h['content'][:250]}...")
        print()


def main() -> None:
    chunks = load_chunks()
    print(f"[smart_merge_eval] loaded {len(chunks)} chunks")
    print()

    from service.rag.retrieval.retriever import _ADJACENT_GAP, _MERGE_MAX_CHARS
    print(f"파라미터: GAP={_ADJACENT_GAP}, MAX_CHARS={_MERGE_MAX_CHARS}")
    print()

    print(sep)
    print("=== 병합 가능 쌍 통계 ===")
    stats = simulate_merge(chunks, gap=_ADJACENT_GAP)
    print(f"  총 청크 수              : {stats['total_chunks']:,}")
    print(f"  연속 청크 쌍(분석 대상) : {stats['total_consecutive_pairs']:,}")
    print(f"  병합 가능 쌍            : {stats['mergeable_pairs']:,}  ({stats['merge_rate']:.1%})")
    print(f"  길이 초과로 미병합      : {stats['blocked_by_length']:,}")
    print()

    print(sep)
    print("=== 병합 전/후 미리보기 ===")
    demo_merge(chunks)


if __name__ == "__main__":
    main()
