"""
검색 전략 A/B 비교 스크립트

미리 정의된 전략 조합으로 recall@k, keyword_hit_rate, diversity, avg_similarity를
비교해 콘솔 테이블로 출력하고 JSON 리포트를 저장한다.

사용:
  python -m service.rag.eval.ab_compare [--dataset eval_dataset.json] [--top-k 5] [--limit 10]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = Path(__file__).parent / "eval_dataset.json"
DEFAULT_REPORT_DIR = ROOT / "data" / "reports"

# 비교할 전략 조합 정의
STRATEGIES = [
    {
        "name": "baseline",
        "desc": "기본 벡터 검색 (하이브리드)",
        "kwargs": {},
    },
    {
        "name": "score_norm",
        "desc": "Score Normalization",
        "kwargs": {"use_score_norm": True},
    },
    {
        "name": "multi_query",
        "desc": "Multi-query Retrieval",
        "kwargs": {"use_multi_query": True, "multi_query_variants": 3},
    },
    {
        "name": "fusion",
        "desc": "Fusion Retrieval (BM25+벡터 RRF)",
        "kwargs": {"use_fusion": True},
    },
    {
        "name": "hyde",
        "desc": "HyDE",
        "kwargs": {"use_hyde": True},
    },
    {
        "name": "neural_reranker",
        "desc": "Neural Reranker (Cross-Encoder)",
        "kwargs": {"use_neural_reranker": True},
    },
    {
        "name": "mmr",
        "desc": "MMR (λ=0.7)",
        "kwargs": {"use_mmr": True, "mmr_lambda": 0.7},
    },
    {
        "name": "score_norm+neural",
        "desc": "Score Norm + Neural Reranker",
        "kwargs": {"use_score_norm": True, "use_neural_reranker": True},
    },
]


def _run_strategy(retriever, questions: list[dict], top_k: int, committee: str | None, kwargs: dict) -> dict:
    from service.rag.eval.recall_eval import evaluate as eval_recall

    total_khr = 0.0
    total_div = 0.0
    total_sim = 0.0
    total_hit = 0
    n = 0

    for row in questions:
        q = str(row.get("question", "")).strip()
        if not q:
            continue
        expected = [str(x) for x in row.get("expected_source_ids", [])]
        try:
            results = retriever.search(q, top_k=top_k, committee=committee, **kwargs)
        except Exception as e:
            print(f"  [warn] {q[:40]}: {e}")
            continue

        m = eval_recall(q, results, k=top_k)
        total_khr += m.get("keyword_hit_rate", 0.0)
        total_div += m.get("diversity", 0.0)
        total_sim += m.get("avg_similarity", 0.0)

        if expected:
            found = [r.get("source_id", "") for r in results]
            if any(e in found for e in expected):
                total_hit += 1

        n += 1

    if n == 0:
        return {"n": 0}

    return {
        "n": n,
        "keyword_hit_rate": round(total_khr / n, 3),
        "diversity": round(total_div / n, 3),
        "avg_similarity": round(total_sim / n, 4),
        "expected_hit_rate": round(total_hit / n, 3) if any(r.get("expected_source_ids") for r in questions) else None,
    }


def run_ab_compare(
    dataset_path: Path = DEFAULT_DATASET,
    top_k: int = 5,
    committee: str | None = "외교통일위원회",
    limit: int | None = None,
    strategies: list[dict] | None = None,
    save_report: bool = True,
) -> dict:
    from service.rag.models.config import EmbeddingModelType
    from service.rag.retrieval.retriever import Retriever

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if limit:
        payload = payload[:limit]

    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    strats = strategies or STRATEGIES

    print(f"[ab_compare] {len(payload)}개 질문 × {len(strats)}개 전략 비교")
    print(f"  top_k={top_k}  committee={committee}\n")

    results: dict[str, dict] = {}

    for s in strats:
        name = s["name"]
        print(f"  [{name}] {s['desc']} ...")
        m = _run_strategy(retriever, payload, top_k, committee, s["kwargs"])
        results[name] = {**s, "metrics": m}
        if m.get("n", 0) > 0:
            print(
                f"    kw_hit={m['keyword_hit_rate']:.3f}  "
                f"div={m['diversity']:.3f}  "
                f"avg_sim={m['avg_similarity']:.4f}"
                + (f"  expected_hit={m['expected_hit_rate']:.3f}" if m.get("expected_hit_rate") is not None else "")
            )

    # 비교 테이블 출력
    print("\n" + "=" * 80)
    print(f"{'전략':<24} {'kw_hit':>8} {'diversity':>10} {'avg_sim':>10} {'exp_hit':>9}")
    print("-" * 80)

    baseline_khr = results.get("baseline", {}).get("metrics", {}).get("keyword_hit_rate", 0.0)

    for s in strats:
        name = s["name"]
        m = results[name]["metrics"]
        if m.get("n", 0) == 0:
            print(f"  {name:<22} (결과 없음)")
            continue
        khr = m["keyword_hit_rate"]
        delta = khr - baseline_khr
        delta_str = f"({delta:+.3f})" if name != "baseline" else ""
        exp_str = f"{m['expected_hit_rate']:.3f}" if m.get("expected_hit_rate") is not None else "  — "
        print(
            f"  {name:<22} {khr:>7.3f}{delta_str:<8} {m['diversity']:>10.3f} "
            f"{m['avg_similarity']:>10.4f} {exp_str:>9}"
        )

    print("=" * 80)

    report = {
        "timestamp": datetime.now().isoformat(),
        "dataset": str(dataset_path.name),
        "n_questions": len(payload),
        "top_k": top_k,
        "committee": committee,
        "results": results,
    }

    if save_report:
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = DEFAULT_REPORT_DIR / f"ab_compare_{ts}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[ab_compare] 리포트 저장: {out}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--committee", type=str, default="외교통일위원회")
    parser.add_argument("--limit", type=int, default=None, help="테스트용: 처음 N개만 평가")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    run_ab_compare(
        dataset_path=args.dataset,
        top_k=args.top_k,
        committee=args.committee or None,
        limit=args.limit,
        save_report=not args.no_save,
    )
