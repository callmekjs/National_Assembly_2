"""
LLM 평가 실행기 — /query 엔드포인트를 호출하고 결과를 기록한다.

사용법:
    python eval/run_eval.py                    # 전체 75문항
    python eval/run_eval.py --ids eval_001,eval_005   # 특정 문항만
    python eval/run_eval.py --dry-run          # API 호출 없이 JSON 구조만 확인
    python eval/run_eval.py --append           # 기존 결과에 누락 항목만 추가

결과: eval/results_YYYYMMDD_HHMMSS.json 에 저장
      llm_evaluation.md 의 ## 테스트 결과 섹션 자동 갱신
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import requests

API_BASE = "http://localhost:8001"
QUESTIONS_FILE = Path(__file__).parent / "questions.json"
EVAL_MD = Path(__file__).parent.parent / "llm_evaluation.md"
RESULTS_DIR = Path(__file__).parent / "results"

LATENCY_WARN_MS = 10_000   # p95 목표 10초
LATENCY_FAIL_MS = 20_000   # 이 이상은 타임아웃 수준


def load_questions(ids: list[str] | None = None) -> list[dict]:
    qs = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if ids:
        qs = [q for q in qs if q["id"] in ids]
    return qs


def call_api(query: str, committee: str | None = None, top_k: int = 4, retries: int = 3) -> dict:
    payload = {
        "question": query,
        "committee": committee,
        "top_k": top_k,
        "use_fusion": True,
        "use_neural_reranker": True,
    }
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        resp = requests.post(f"{API_BASE}/query", json=payload, timeout=180)
        wall_ms = (time.perf_counter() - t0) * 1000
        if resp.status_code == 429:
            wait = 10 * attempt
            print(f"  ⚠️  rate limit (429), {wait}s 대기 후 재시도 ({attempt}/{retries})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        data["_wall_ms"] = wall_ms
        return data
    raise RuntimeError(f"rate limit 재시도 {retries}회 모두 실패")


def auto_grade(q: dict, resp: dict) -> dict:
    """자동 채점 가능한 항목만 채점. 나머지는 None(수동 채점 필요)."""
    answer = resp.get("answer", "")
    citations = resp.get("citations", [])
    grounding = resp.get("grounding_level", "NONE")
    latency = resp.get("latency_total_ms") or resp.get("_wall_ms", 0)

    scores: dict = {}

    # 1. 속도 채점
    scores["latency_ok"] = latency < LATENCY_WARN_MS
    scores["latency_ms"] = round(latency)

    # 2. 근거 생성 여부 (grounding_level)
    scores["grounding_level"] = grounding
    scores["grounding_ok"] = grounding in ("FULL", "PARTIAL")

    # 3. 인용 수
    scores["citation_count"] = len(citations)

    # 4. 키워드 포함 여부
    expected_kw = q.get("expected_keywords") or []
    if expected_kw:
        hit = sum(1 for kw in expected_kw if kw in answer)
        scores["keyword_hit"] = hit
        scores["keyword_total"] = len(expected_kw)
        scores["keyword_ok"] = hit == len(expected_kw)
    else:
        scores["keyword_ok"] = None

    # 5. must_not_include — 설명 문자열(anti-pattern 묘사)이므로 자동 판정 불가
    #    수동 채점자에게 체크 항목을 전달하는 용도로만 보존
    must_not = q.get("must_not_include") or []
    scores["must_not_violations"] = []
    scores["must_not_ok"] = None  # 수동 채점 필요
    scores["must_not_checklist"] = must_not  # 채점자 참고용

    # 6. 모르는 질문 대응 (type=unanswerable)
    # 허위 전제 질문(hallucination trap)도 unanswerable로 분류됨
    if q.get("type") == "unanswerable":
        refusal_phrases = [
            "찾을 수 없", "없습니다", "확인되지 않", "회의록에", "데이터에",
            "포함되어 있지 않", "기록이 없", "해당 내용", "확인 불가",
        ]
        refused = any(p in answer for p in refusal_phrases) and grounding in ("NONE", "REFUSED")
        scores["unanswerable_refused"] = refused

    # 8. 수치 포함 여부 (type=numerical_fact)
    if q.get("type") == "numerical_fact":
        has_number = bool(re.search(r"\d[\d,억만천백십%]", answer))
        scores["numerical_found"] = has_number

    # 7. 발언자 attribution 자동 체크
    expected_speaker = q.get("expected_speaker")
    if expected_speaker:
        scores["speaker_mentioned"] = expected_speaker in answer

    return scores


def format_result_row(q: dict, resp: dict, scores: dict) -> str:
    qid = q["id"]
    qtype = q["type"]
    query = q["query"][:35] + "…" if len(q["query"]) > 35 else q["query"]
    lat = scores.get("latency_ms", "?")
    grnd = scores.get("grounding_level", "?")
    cites = scores.get("citation_count", "?")
    lat_icon = "✅" if scores.get("latency_ok") else "⚠️"
    kw_icon = "✅" if scores.get("keyword_ok") else ("⚠️" if scores.get("keyword_ok") is False else "—")
    return f"| {qid} | {qtype} | {query} | {lat}ms {lat_icon} | {grnd} | {cites} | {kw_icon} | — |"


def run(args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    questions = load_questions(args.ids.split(",") if args.ids else None)

    if args.dry_run:
        print(f"[dry-run] {len(questions)}개 문항 로드 완료. API 호출 없음.")
        for q in questions:
            print(f"  {q['id']} [{q['type']}] {q['query'][:60]}")
        return

    # 서버 헬스 체크
    try:
        hc = requests.get(f"{API_BASE}/health", timeout=5)
        hc.raise_for_status()
        print(f"✅ API 서버 연결 확인 ({API_BASE})")
    except Exception as e:
        print(f"❌ API 서버 응답 없음: {e}")
        print("   서버를 먼저 시작하세요: uvicorn api.main:app --reload")
        sys.exit(1)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        print(f"\n[{i}/{len(questions)}] {qid}: {q['query'][:55]}…")

        try:
            resp = call_api(q["query"], committee=q.get("committee"), top_k=4)
            scores = auto_grade(q, resp)

            lat = scores["latency_ms"]
            grnd = scores["grounding_level"]
            lat_icon = "✅" if scores["latency_ok"] else "⚠️"
            print(f"  → {lat}ms {lat_icon}  grounding={grnd}  citations={scores['citation_count']}")

            if q.get("type") == "unanswerable":
                refused = scores.get("unanswerable_refused", False)
                print(f"  → 거절 여부: {'✅ 거절함' if refused else '❌ 거절 안 함'}")

            result = {
                "id": qid,
                "query": q["query"],
                "type": q["type"],
                "answer": resp.get("answer", ""),
                "grounding_level": grnd,
                "citation_count": scores["citation_count"],
                "citations": [
                    {
                        "index": c.get("index"),
                        "speaker": c.get("speaker"),
                        "date": c.get("date"),
                        "content_preview": c.get("content_preview"),
                    }
                    for c in resp.get("citations", [])
                ],
                "scores": scores,
                "grading_notes": q.get("grading_notes", ""),
                "manual_grades": {
                    "faithfulness": None,
                    "speaker_accuracy": None,
                    "completeness": None,
                    "overall": None,
                    "notes": "",
                },
            }
            results.append(result)

        except requests.exceptions.Timeout:
            print(f"  ❌ TIMEOUT (>60s)")
            results.append({"id": qid, "query": q["query"], "error": "TIMEOUT"})
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({"id": qid, "query": q["query"], "error": str(e)})

        time.sleep(2.0)

    # JSON 저장
    prefix = getattr(args, "prefix", None) or "results"
    out_path = RESULTS_DIR / f"{prefix}_{run_ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 결과 저장: {out_path}")

    # 마크다운 테이블 생성
    print("\n" + "=" * 60)
    print("## 테스트 결과 요약")
    print("=" * 60)

    total = len([r for r in results if "error" not in r])
    latency_ok = sum(1 for r in results if r.get("scores", {}).get("latency_ok"))
    grounding_ok = sum(1 for r in results if r.get("scores", {}).get("grounding_ok"))
    unanswerable_refused = sum(
        1 for r in results
        if r.get("type") == "unanswerable" and r.get("scores", {}).get("unanswerable_refused")
    )
    unanswerable_total = sum(1 for q in questions if q["type"] == "unanswerable")

    print(f"\n총 {total}문항 실행")
    print(f"- p95 latency 기준(10s) 통과: {latency_ok}/{total}")
    print(f"- Grounding FULL/PARTIAL: {grounding_ok}/{total}")
    if unanswerable_total:
        print(f"- 모르는 질문 거절: {unanswerable_refused}/{unanswerable_total}")

    print("\n| ID | 유형 | 질문 | 응답시간 | Grounding | 인용수 | 키워드 | 수동점수 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            print(f"| {r['id']} | — | {r['query'][:35]} | ❌ {r['error']} | — | — | — | — |")
        else:
            q = next((x for x in questions if x["id"] == r["id"]), {})
            row = format_result_row(q, {}, r.get("scores", {}))
            print(row)

    print(f"\n결과 파일: {out_path}")
    print("수동 채점은 results/*.json 파일의 manual_grades 필드를 직접 편집하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 평가 실행기")
    parser.add_argument("--ids", help="실행할 문항 ID (쉼표 구분), 예: eval_001,eval_005")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 문항 목록만 출력")
    parser.add_argument("--append", action="store_true", help="기존 결과에 누락 항목만 추가")
    parser.add_argument("--prefix", default="results", help="결과 파일명 접두사 (기본: results)")
    args = parser.parse_args()
    run(args)
