from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from service.rag.models.config import EmbeddingModelType
from service.rag.retrieval.retriever import Retriever

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES = Path(__file__).resolve().parent / "eval_queries.json"


def evaluate(queries_path: Path, top_k: int = 3) -> None:
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("eval query file must be a list")

    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    total = 0
    pass_count = 0
    expected_total = 0
    expected_hits = 0
    reciprocal_rank_sum = 0.0

    for idx, row in enumerate(payload, start=1):
        query = str(row.get("query", "")).strip()
        keywords = [str(x).strip() for x in row.get("keywords", []) if str(x).strip()]
        expected_sources = [str(x).strip() for x in row.get("expected_source_ids", []) if str(x).strip()]
        if not query:
            continue
        total += 1
        results = retriever.search(query, top_k=top_k)
        found_sources = [str(r.get("source_id", "")) for r in results]
        joined = " ".join((r.get("content", "") or "") for r in results).lower()
        keyword_hit = any(k.lower() in joined for k in keywords) if keywords else False

        expected_hit = False
        rr = 0.0
        if expected_sources:
            expected_total += 1
            for rank, source in enumerate(found_sources, start=1):
                if source in expected_sources:
                    expected_hit = True
                    rr = 1.0 / rank
                    break
            if expected_hit:
                expected_hits += 1
            reciprocal_rank_sum += rr

        # expected_source_ids가 있으면 그것을 우선 PASS 기준으로 사용
        hit = expected_hit if expected_sources else keyword_hit
        if hit:
            pass_count += 1
        print(f"[{idx:02d}] {'PASS' if hit else 'FAIL'} query={query}")
        if expected_sources:
            print(f"      expected={expected_sources} found={found_sources[:top_k]} rr={rr:.3f}")

    score = (pass_count / total * 100.0) if total else 0.0
    print("\n[evaluate_retrieval] done")
    print(f"- total_queries: {total}")
    print(f"- passed: {pass_count}")
    print(f"- score_percent: {score:.1f}")
    if expected_total:
        recall_at_k = expected_hits / expected_total * 100.0
        mrr = reciprocal_rank_sum / expected_total
        print(f"- expected_labeled_queries: {expected_total}")
        print(f"- recall@{top_k}: {recall_at_k:.1f}")
        print(f"- mrr@{top_k}: {mrr:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="간단 검색 품질 회귀 평가")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    args = parser.parse_args()
    os.environ["PG_PORT"] = str(args.pg_port)
    evaluate(args.queries, top_k=args.top_k)


if __name__ == "__main__":
    main()
