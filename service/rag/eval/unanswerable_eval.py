"""
정답 없는 질문 10개 평가 (Grounding Check 기준 6)
# ruff: noqa: E402

목적: 코퍼스(외교통일위원회 55건)에 답이 없는 질문에 대해
      RAG 파이프라인이 무리한 답변을 하지 않는지 확인.

평가 기준:
  PASS  — 거부 응답이거나 ⚠/ℹ 경고 포함 또는 "확인 불가" 표현 있음
  WARN  — 짧지만 경고 없이 애매한 답변
  FAIL  — 자신 있게 틀린 정보를 제공

실행:
  python -m service.rag.eval.unanswerable_eval
  python -m service.rag.eval.unanswerable_eval --pg-port 5433 --top-k 5
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 출력
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.parent.parent

# ── 정답 없는 질문 10개 ──────────────────────────────────────────
# 두 가지 유형:
#   A) 코퍼스 외 주제 (완전 OOD)
#   B) 주제는 외교통일이지만 코퍼스에 해당 정보 없음

UNANSWERABLE_QUESTIONS = [
    # A) 완전 OOD
    {
        "id": "ood_01",
        "question": "삼성전자의 2023년 연간 영업이익은 얼마인가요?",
        "type": "OOD",
        "reason": "기업 실적 — 외교통일위원회 회의록과 무관",
    },
    {
        "id": "ood_02",
        "question": "ChatGPT는 어떤 방식으로 언어를 생성하나요?",
        "type": "OOD",
        "reason": "AI 기술 설명 — 회의록과 무관",
    },
    {
        "id": "ood_03",
        "question": "소방관 처우 개선을 위한 행정안전위원회 논의 내용을 알려주세요.",
        "type": "OOD",
        "reason": "다른 위원회(행정안전) 주제",
    },
    {
        "id": "ood_04",
        "question": "기후변화 협약에 대한 환경부 장관의 입장은 무엇인가요?",
        "type": "OOD",
        "reason": "환경 정책 — 외교통일위원회 주제 아님",
    },
    {
        "id": "ood_05",
        "question": "한국 주식시장에서 코스피 지수가 3000을 넘은 날짜는 언제인가요?",
        "type": "OOD",
        "reason": "금융 데이터 — 회의록과 무관",
    },
    # B) 외교통일 주제이지만 코퍼스에 없는 구체 정보
    {
        "id": "corpus_01",
        "question": "2018년 남북 교류협력 사업이 중단된 정확한 날짜와 이유를 회의록 근거로 설명해주세요.",
        "type": "IN_TOPIC_NOT_IN_CORPUS",
        "reason": "2018년 특정 날짜 정보 — 55건 코퍼스에 없을 가능성 높음",
    },
    {
        "id": "corpus_02",
        "question": "외교통일위원회에서 코로나19 백신 외교를 다룬 회의가 있었나요?",
        "type": "IN_TOPIC_NOT_IN_CORPUS",
        "reason": "코로나 백신 외교 — 코퍼스에 없는 주제",
    },
    {
        "id": "corpus_03",
        "question": "통일부 장관이 2022년 국정감사에서 탈북민 지원 예산에 대해 구체적으로 언급한 금액은?",
        "type": "IN_TOPIC_NOT_IN_CORPUS",
        "reason": "2022년 국감 특정 수치 — 코퍼스 범위 밖",
    },
    {
        "id": "corpus_04",
        "question": "외교통일위원회에서 한국의 유엔 인권이사회 이사국 선출 문제를 논의한 적 있나요?",
        "type": "IN_TOPIC_NOT_IN_CORPUS",
        "reason": "유엔 인권이사회 선출 — 코퍼스에 없을 가능성",
    },
    {
        "id": "corpus_05",
        "question": "북한의 ICBM 발사 직후 외교통일위원회 긴급 현안 질의에서 오간 구체적 발언을 인용해주세요.",
        "type": "IN_TOPIC_NOT_IN_CORPUS",
        "reason": "긴급 현안 질의 특정 발언 — 코퍼스 포함 여부 불명확",
    },
]

# ── 거부 / 경고 판별 ─────────────────────────────────────────────
_REFUSAL_PATTERNS = [
    r"찾지 못했습니다",
    r"확인되지 않",
    r"관련 내용을 찾을 수 없",
    r"답변하기 어렵",
    r"답변을 생성하기 어렵",
    r"충분하지 않",
    r"회의록에서 확인.*불가",
    r"검색된.*자료가 부족",
    r"회의록에.*없습니다",
    r"정보가 없습니다",
]

_WARNING_MARKERS = ["⚠", "ℹ", "*(출처 미확인)*", "*(근거 미확인)*"]


def _grade(answer: str) -> str:
    """
    PASS  — 거부 or 경고 표현 있음
    WARN  — 짧음 (< 150자) 하지만 경고 없음
    FAIL  — 자신 있게 답변 (경고 없이 200자 이상)
    """
    if not answer or not answer.strip():
        return "PASS"

    text = answer.strip()

    for pat in _REFUSAL_PATTERNS:
        if re.search(pat, text):
            return "PASS"

    for marker in _WARNING_MARKERS:
        if marker in text:
            return "PASS"

    if len(text) < 150:
        return "WARN"

    return "FAIL"


# ── 파이프라인 실행 ──────────────────────────────────────────────

def run_pipeline(question: str, pg_port: int, top_k: int) -> dict:
    """LangGraph RAG 파이프라인으로 답변 생성."""
    import os
    os.environ.setdefault("PG_PORT", str(pg_port))

    from graph.app_graph import build_graph

    graph = build_graph()
    meta = {
        "top_k": top_k,
        "rerank_n": 3,
        "committee": "외교통일위원회",
    }
    result = graph.invoke({"question": question, "meta": meta})
    answer = result.get("draft_answer") or result.get("answer") or ""
    grounding_level = result.get("grounding_level", "")
    docs = result.get("reranked") or result.get("retrieved") or []
    return {
        "answer": answer,
        "grounding_level": grounding_level,
        "doc_count": len(docs),
    }


# ── 평가 실행 ────────────────────────────────────────────────────

def evaluate(pg_port: int = 5433, top_k: int = 5) -> dict:
    results = []
    pass_count = warn_count = fail_count = 0

    print(f"\n{'='*60}")
    print(f"정답 없는 질문 평가 ({len(UNANSWERABLE_QUESTIONS)}개)")
    print(f"pg_port={pg_port}  top_k={top_k}")
    print(f"{'='*60}\n")

    for q in UNANSWERABLE_QUESTIONS:
        print(f"[{q['id']}] {q['question'][:60]}...")
        try:
            res = run_pipeline(q["question"], pg_port=pg_port, top_k=top_k)
            grade = _grade(res["answer"])
        except Exception as e:
            res = {"answer": f"ERROR: {e}", "grounding_level": "", "doc_count": 0}
            grade = "WARN"

        if grade == "PASS":
            pass_count += 1
        elif grade == "WARN":
            warn_count += 1
        else:
            fail_count += 1

        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[grade]
        print(f"  {icon} {grade}  docs={res['doc_count']}  level={res['grounding_level']}")
        print(f"  답변: {res['answer'][:120].strip()!r}\n")

        results.append({
            **q,
            "grade": grade,
            "doc_count": res["doc_count"],
            "grounding_level": res["grounding_level"],
            "answer_preview": res["answer"][:300],
        })

    total = len(UNANSWERABLE_QUESTIONS)
    pass_rate = pass_count / total * 100

    print(f"\n{'='*60}")
    print(f"결과: PASS={pass_count}/{total} ({pass_rate:.0f}%)  WARN={warn_count}  FAIL={fail_count}")

    if pass_rate >= 80:
        verdict = "✅ 기준 충족 (80% 이상 거부)"
    elif pass_rate >= 60:
        verdict = "⚠️ 부분 충족 (60~79% 거부)"
    else:
        verdict = "❌ 기준 미달 (<60% 거부)"
    print(f"판정: {verdict}")
    print(f"{'='*60}\n")

    report = {
        "evaluated_at": datetime.now().isoformat(),
        "pg_port": pg_port,
        "top_k": top_k,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "pass_rate": round(pass_rate, 1),
        "verdict": verdict,
        "results": results,
    }

    out_path = ROOT / "data" / "reports" / f"unanswerable_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"리포트 저장: {out_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="정답 없는 질문 평가")
    parser.add_argument("--pg-port", type=int, default=5433)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true",
                        help="파이프라인 실행 없이 질문 목록만 출력")
    args = parser.parse_args()

    if args.dry_run:
        print(f"\n정답 없는 질문 {len(UNANSWERABLE_QUESTIONS)}개:\n")
        for q in UNANSWERABLE_QUESTIONS:
            print(f"  [{q['id']}] ({q['type']})")
            print(f"    Q: {q['question']}")
            print(f"    이유: {q['reason']}\n")
        sys.exit(0)

    sys.path.insert(0, str(ROOT))
    evaluate(pg_port=args.pg_port, top_k=args.top_k)
