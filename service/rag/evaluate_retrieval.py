from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from service.rag.models.config import EmbeddingModelType
from service.rag.retrieval.retriever import Retriever

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES = Path(__file__).resolve().parent / "eval_queries_fixed.json"


def _new_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "passed": 0,
        "expected_total": 0,
        "expected_hits": 0,
        "rr_sum": 0.0,
    }


def evaluate(
    queries_path: Path,
    top_k: int = 3,
    alpha: float = 0.8,
    committee: str | None = None,
    use_reranker: bool = False,
    balance_speakers: bool = False,
    candidate_multiplier: int = 50,
) -> dict[str, Any]:
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("eval query file must be a list")

    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    total = 0
    pass_count = 0
    expected_total = 0
    expected_hits = 0
    reciprocal_rank_sum = 0.0
    type_stats: dict[str, dict[str, Any]] = {}

    for idx, row in enumerate(payload, start=1):
        query = str(row.get("query", "")).strip()
        query_type = str(row.get("type", "summary")).strip().lower() or "summary"
        keywords = [str(x).strip() for x in row.get("keywords", []) if str(x).strip()]
        expected_sources = [str(x).strip() for x in row.get("expected_source_ids", []) if str(x).strip()]
        if not query:
            continue
        bucket = type_stats.setdefault(query_type, _new_bucket())
        total += 1
        bucket["total"] += 1
        results = retriever.search(
            query,
            top_k=top_k,
            alpha=alpha,
            committee=committee,
            use_reranker=use_reranker,
            balance_speakers=balance_speakers,
            candidate_multiplier=candidate_multiplier,
        )
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
            bucket["passed"] += 1
        if expected_sources:
            bucket["expected_total"] += 1
            bucket["rr_sum"] += rr
            if expected_hit:
                bucket["expected_hits"] += 1
        print(f"[{idx:02d}] {'PASS' if hit else 'FAIL'} type={query_type} query={query}")
        if expected_sources:
            print(f"      expected={expected_sources} found={found_sources[:top_k]} rr={rr:.3f}")

    score = (pass_count / total * 100.0) if total else 0.0
    print("\n[evaluate_retrieval] done")
    print(f"- total_queries: {total}")
    print(f"- passed: {pass_count}")
    print(f"- score_percent: {score:.1f}")
    report: dict[str, Any] = {
        "total_queries": total,
        "passed": pass_count,
        "score_percent": round(score, 1),
        "top_k": top_k,
        "per_type": {},
    }
    if expected_total:
        recall_at_k = expected_hits / expected_total * 100.0
        mrr = reciprocal_rank_sum / expected_total
        print(f"- expected_labeled_queries: {expected_total}")
        print(f"- recall@{top_k}: {recall_at_k:.1f}")
        print(f"- mrr@{top_k}: {mrr:.3f}")
        report["expected_labeled_queries"] = expected_total
        report[f"recall@{top_k}"] = round(recall_at_k, 1)
        report[f"mrr@{top_k}"] = round(mrr, 3)

    print("\n[evaluate_retrieval] by_type")
    for t in sorted(type_stats.keys()):
        b = type_stats[t]
        type_score = (b["passed"] / b["total"] * 100.0) if b["total"] else 0.0
        line = f"- {t}: score={type_score:.1f}% ({b['passed']}/{b['total']})"
        type_report: dict[str, Any] = {
            "total": b["total"],
            "passed": b["passed"],
            "score_percent": round(type_score, 1),
        }
        if b["expected_total"]:
            t_recall = b["expected_hits"] / b["expected_total"] * 100.0
            t_mrr = b["rr_sum"] / b["expected_total"]
            line += f", recall@{top_k}={t_recall:.1f}, mrr@{top_k}={t_mrr:.3f}"
            type_report[f"recall@{top_k}"] = round(t_recall, 1)
            type_report[f"mrr@{top_k}"] = round(t_mrr, 3)
        print(line)
        report["per_type"][t] = type_report
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="간단 검색 품질 회귀 평가")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=0.8, help="vector vs lexical blend (1.0=vector only)")
    parser.add_argument("--committee", default="", help="committee exact match filter")
    parser.add_argument("--use-reranker", action="store_true")
    parser.add_argument("--balance-speakers", action="store_true")
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=50,
        help="벡터 후보 배수(top_k×이 값 이상에서 하이브리드 재정렬). 긴 회의 후반 청킹 등은 순위가 뒤로 밀릴 수 있어 기본값을 크게 둠",
    )
    parser.add_argument("--baseline-score", type=float, default=None)
    parser.add_argument("--baseline-recall", type=float, default=None)
    parser.add_argument("--baseline-mrr", type=float, default=None)
    parser.add_argument("--report-out", type=Path, default=None, help="write evaluation report json")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    args = parser.parse_args()
    os.environ["PG_PORT"] = str(args.pg_port)
    report = evaluate(
        args.queries,
        top_k=args.top_k,
        alpha=args.alpha,
        committee=args.committee or None,
        use_reranker=args.use_reranker,
        balance_speakers=args.balance_speakers,
        candidate_multiplier=args.candidate_multiplier,
    )
    print("\n[evaluate_retrieval] delta_vs_baseline")
    if args.baseline_score is not None:
        delta_score = float(report.get("score_percent", 0.0)) - float(args.baseline_score)
        print(f"- score_percent_delta: {delta_score:+.1f}")
    if args.baseline_recall is not None:
        cur = float(report.get(f"recall@{args.top_k}", 0.0))
        delta_recall = cur - float(args.baseline_recall)
        print(f"- recall@{args.top_k}_delta: {delta_recall:+.1f}")
    if args.baseline_mrr is not None:
        cur = float(report.get(f"mrr@{args.top_k}", 0.0))
        delta_mrr = cur - float(args.baseline_mrr)
        print(f"- mrr@{args.top_k}_delta: {delta_mrr:+.3f}")
    if args.report_out:
        args.report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"- report_saved: {args.report_out}")


if __name__ == "__main__":
    main()
