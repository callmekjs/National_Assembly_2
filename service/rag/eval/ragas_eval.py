"""
RAGAS 기반 RAG 파이프라인 자동 평가

측정 지표:
  faithfulness      — 답변이 검색 문서에 충실한가 (hallucination 감지)
  answer_relevancy  — 답변이 질문과 관련있는가
  context_precision — 검색된 context 중 실제 관련있는 비율
  context_recall    — context가 정답에 필요한 정보를 포함하는가 (ground_truth 있는 항목만)

사용:
  python -m service.rag.eval.ragas_eval [--dataset eval_dataset.json] [--top-k 5] [--limit 10]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = Path(__file__).parent / "eval_dataset.json"
DEFAULT_REPORT_DIR = ROOT / "data" / "reports"


def _retrieve(retriever, question: str, top_k: int, committee: str | None) -> list[str]:
    results = retriever.search(
        question,
        top_k=top_k,
        committee=committee,
        include_metadata=True,
    )
    return [r.get("content", "") for r in results if r.get("content")]


def _generate(question: str, contexts: list[str]) -> str:
    from datetime import date as date_cls
    from service.llm.llm_client import chat
    from service.llm.prompt_templates import build_system_prompt, build_user_prompt

    context_str = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
    system = build_system_prompt(question)
    user = build_user_prompt(question, context_str, reference_date=date_cls.today())
    return chat(system, user, max_tokens=512)


def run_ragas_eval(
    dataset_path: Path = DEFAULT_DATASET,
    top_k: int = 5,
    committee: str | None = "외교통일위원회",
    limit: int | None = None,
    save_report: bool = True,
) -> dict:
    from service.rag.models.config import EmbeddingModelType
    from service.rag.retrieval.retriever import Retriever

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if limit:
        payload = payload[:limit]

    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    questions, answers, contexts_list, ground_truths = [], [], [], []
    has_ground_truth = False

    print(f"[ragas_eval] {len(payload)}개 질문 처리 중...")
    for i, row in enumerate(payload, 1):
        q = str(row.get("question", "")).strip()
        gt = str(row.get("ground_truth", "")).strip()
        if not q:
            continue

        print(f"  [{i:02d}/{len(payload):02d}] {q[:60]}")

        try:
            contexts = _retrieve(retriever, q, top_k, committee)
            if not contexts:
                print(f"         → 검색 결과 없음, 건너뜀")
                continue
            answer = _generate(q, contexts)
        except Exception as e:
            print(f"         → 오류: {e}, 건너뜀")
            continue

        questions.append(q)
        answers.append(answer)
        contexts_list.append(contexts)
        if gt:
            ground_truths.append(gt)
            has_ground_truth = True
        else:
            ground_truths.append("")

    if not questions:
        print("[ragas_eval] 처리된 질문 없음")
        return {}

    # RAGAS 평가
    print(f"\n[ragas_eval] RAGAS 평가 시작 ({len(questions)}개)...")
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision

    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
    }

    metrics = [faithfulness, answer_relevancy, context_precision]

    if has_ground_truth:
        from ragas.metrics import context_recall
        filled_gt = [gt if gt else "정보 없음" for gt in ground_truths]
        data["ground_truth"] = filled_gt
        metrics.append(context_recall)
        print("  → context_recall 포함 (ground_truth 있음)")

    dataset = Dataset.from_dict(data)

    try:
        result = evaluate(dataset, metrics=metrics, raise_exceptions=False)
    except Exception as e:
        print(f"[ragas_eval] RAGAS 실패: {e}")
        return {"error": str(e)}

    # 결과 추출
    scores = {}
    result_df = result.to_pandas()
    for col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if col in result_df.columns:
            val = float(result_df[col].mean())
            scores[col] = round(val, 4)

    report = {
        "timestamp": datetime.now().isoformat(),
        "dataset": str(dataset_path.name),
        "n_questions": len(questions),
        "top_k": top_k,
        "committee": committee,
        "scores": scores,
    }

    print("\n[ragas_eval] === 결과 ===")
    for k, v in scores.items():
        if v != v:  # NaN guard
            print(f"  {k:<22} (측정 불가 — NaN)")
            continue
        bar = "█" * int(v * 20) + "░" * (20 - int(v * 20))
        print(f"  {k:<22} {bar} {v:.4f}")

    if save_report:
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = DEFAULT_REPORT_DIR / f"ragas_{ts}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[ragas_eval] 리포트 저장: {out}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--committee", type=str, default="외교통일위원회")
    parser.add_argument("--limit", type=int, default=None, help="테스트용: 처음 N개만 평가")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    run_ragas_eval(
        dataset_path=args.dataset,
        top_k=args.top_k,
        committee=args.committee or None,
        limit=args.limit,
        save_report=not args.no_save,
    )
