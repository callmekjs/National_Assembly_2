"""
Hybrid vs Dense-only Recall 비교 평가

alpha=0.75 (Dense 75% + FTS 25%) vs alpha=1.0 (Dense-only) 검색 품질 비교.
DB 연결이 필요하며, 서버 없이 Retriever를 직접 호출한다.

사용법:
    python eval/hybrid_vs_dense_eval.py                    # 전체 75문항
    python eval/hybrid_vs_dense_eval.py --n 20             # 처음 N개만
    python eval/hybrid_vs_dense_eval.py --k 5              # Recall@k 기준
    python eval/hybrid_vs_dense_eval.py --out results/hybrid_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

QUESTIONS_FILE = Path(__file__).parent / "questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

_TOP_K = 5
_ALPHA_HYBRID = 0.75
_ALPHA_DENSE = 1.0


def _load_retriever():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from service.rag.retrieval.retriever import Retriever
    from service.rag.models.config import EmbeddingModelType
    return Retriever(model_type=EmbeddingModelType.BGE_M3, enable_temporal_filter=False)


def _run_search(retriever, query: str, committee: str | None, alpha: float, top_k: int) -> list[dict]:
    return retriever.search_v2(
        query=query,
        top_k=top_k,
        alpha=alpha,
        committee=committee or None,
    )


def _eval(query: str, results: list[dict], k: int) -> dict:
    from service.rag.eval.recall_eval import evaluate
    return evaluate(query, results, k=k)


def _delta(hybrid: dict, dense: dict, key: str) -> str:
    h = hybrid.get(key, 0.0)
    d = dense.get(key, 0.0)
    diff = h - d
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.3f}"


def run(args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    k = args.k

    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if args.n:
        questions = questions[: args.n]

    print(f"Hybrid(α={_ALPHA_HYBRID}) vs Dense-only(α={_ALPHA_DENSE}) — Recall@{k}")
    print(f"총 {len(questions)}개 쿼리\n")

    try:
        retriever = _load_retriever()
    except Exception as e:
        print(f"❌ Retriever 초기화 실패: {e}")
        print("   DB 연결(.env PG_HOST, PG_PORT 등)을 확인하세요.")
        sys.exit(1)

    records: list[dict] = []
    totals_hybrid: dict[str, float] = {"keyword_hit_rate": 0.0, "diversity": 0.0, "avg_similarity": 0.0}
    totals_dense: dict[str, float] = {"keyword_hit_rate": 0.0, "diversity": 0.0, "avg_similarity": 0.0}
    hybrid_wins = 0
    dense_wins = 0
    ties = 0

    header = f"{'ID':<12} {'쿼리':<30} {'KHR(H)':<8} {'KHR(D)':<8} {'Δ KHR':<8} {'SIM(H)':<8} {'SIM(D)':<8} {'승자'}"
    print(header)
    print("-" * len(header))

    for q in questions:
        qid = q["id"]
        query = q["query"]
        committee = q.get("committee")
        short_q = query[:28] + "…" if len(query) > 28 else query

        try:
            t0 = time.perf_counter()
            res_hybrid = _run_search(retriever, query, committee, _ALPHA_HYBRID, k)
            t_hybrid = time.perf_counter() - t0

            t0 = time.perf_counter()
            res_dense = _run_search(retriever, query, committee, _ALPHA_DENSE, k)
            t_dense = time.perf_counter() - t0

            m_h = _eval(query, res_hybrid, k)
            m_d = _eval(query, res_dense, k)

            for key in totals_hybrid:
                totals_hybrid[key] += m_h.get(key, 0.0)
                totals_dense[key] += m_d.get(key, 0.0)

            khr_h = m_h["keyword_hit_rate"]
            khr_d = m_d["keyword_hit_rate"]
            sim_h = m_h["avg_similarity"]
            sim_d = m_d["avg_similarity"]
            d_khr = _delta(m_h, m_d, "keyword_hit_rate")

            if khr_h > khr_d:
                winner = "Hybrid ✓"
                hybrid_wins += 1
            elif khr_d > khr_h:
                winner = "Dense ✓"
                dense_wins += 1
            else:
                winner = "동률"
                ties += 1

            print(
                f"{qid:<12} {short_q:<30} "
                f"{khr_h:<8.3f} {khr_d:<8.3f} {d_khr:<8} "
                f"{sim_h:<8.4f} {sim_d:<8.4f} {winner}"
            )

            records.append({
                "id": qid,
                "query": query,
                "committee": committee,
                "hybrid": {**m_h, "latency_s": round(t_hybrid, 3)},
                "dense": {**m_d, "latency_s": round(t_dense, 3)},
                "winner": winner,
            })

        except Exception as e:
            print(f"{qid:<12} {'ERROR: ' + str(e):<60}")
            records.append({"id": qid, "query": query, "error": str(e)})

    n = len(questions)
    print("\n" + "=" * 60)
    print(f"집계 (N={n})")
    print(f"{'지표':<25} {'Hybrid':>10} {'Dense':>10} {'Δ':>10}")
    print("-" * 55)
    for key in ("keyword_hit_rate", "diversity", "avg_similarity"):
        avg_h = totals_hybrid[key] / n
        avg_d = totals_dense[key] / n
        diff = avg_h - avg_d
        sign = "+" if diff >= 0 else ""
        print(f"{key:<25} {avg_h:>10.4f} {avg_d:>10.4f} {sign+f'{diff:.4f}':>10}")

    print(f"\nKeyword Hit Rate 기준 승패: Hybrid {hybrid_wins} | Dense {dense_wins} | 동률 {ties}")

    out_path = args.out or str(RESULTS_DIR / "hybrid_vs_dense_latest.json")
    Path(out_path).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid vs Dense Recall 비교")
    parser.add_argument("--n", type=int, default=None, help="평가 문항 수 (기본: 전체)")
    parser.add_argument("--k", type=int, default=_TOP_K, help=f"Recall@k 기준 (기본: {_TOP_K})")
    parser.add_argument("--out", type=str, default=None, help="결과 JSON 저장 경로")
    run(parser.parse_args())
