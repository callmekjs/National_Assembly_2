"""
Streamlit (`pages/views/chat.py`)과 동일한 검색 메타로
Retrieve → Rerank → ContextTrim 이 만든 `citations`가
`reranked` 상위 문서의 `source_id`·`chunk_id`와 1:1로 맞는지 검증합니다.

Day 11: 답변 본문 `[n]` 번호는 생성기가 `citations` 길이로 클리핑하며,
참고 자료 블록은 `citations` 순서를 그대로 쓰므로, 이 정합이 UI와 동일합니다.

사용:
    $env:PYTHONIOENCODING='utf-8'; $env:PG_PORT='5433'
    python -m service.rag.verify_streamlit_citation_alignment
"""

from __future__ import annotations

import argparse
import os
import sys

from graph.nodes import context_trim, query_rewrite, rerank, retrieve_pg, router


def _streamlit_like_meta() -> dict:
    """`_init_state` + `_build_search_meta_from_session()` 기본에 맞춤."""
    return {
        "top_k": 8,
        "alpha": 0.75,
        "committee": "외교통일위원회",
        "date_from": "",
        "date_to": "",
        "use_reranker": False,
        "balance_speakers": False,
        "candidate_multiplier": 50,
    }


def verify_retrieval_alignment(state: dict) -> list[str]:
    errors: list[str] = []
    docs = state.get("reranked") or []
    cits = state.get("citations") or []
    if not docs:
        errors.append("reranked 비어 있음")
        return errors
    n = min(5, len(docs))
    if len(cits) != n:
        errors.append(f"citations 길이 {len(cits)} != 예상 {n}")
    for i in range(min(len(cits), n)):
        d = docs[i]
        c = cits[i]
        if (c.get("source_id") or "") != (d.get("source_id") or ""):
            errors.append(f"[{i+1}] source_id 불일치: citation={c.get('source_id')!r} doc={d.get('source_id')!r}")
        if (c.get("chunk_id") or "") != (d.get("chunk_id") or ""):
            errors.append(f"[{i+1}] chunk_id 불일치: citation={c.get('chunk_id')!r} doc={d.get('chunk_id')!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="검색~citations 정합 검증(Streamlit 동일 메타)")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    args = parser.parse_args()
    os.environ["PG_PORT"] = str(args.pg_port)

    questions = (
        "정보 공유 제한 이슈가 언급된 회의가 있나?",
        "통일부 장관 관련 주요 질의는?",
    )
    want = "20260423_56594_56594"

    failures = 0
    for q in questions:
        state: dict = {
            "question": q,
            "meta": _streamlit_like_meta(),
        }
        router.run(state)
        query_rewrite.run(state)
        retrieve_pg.run(state)
        rerank.run(state)
        context_trim.run(state)

        errs = verify_retrieval_alignment(state)
        top_sources = [(d.get("source_id"), d.get("chunk_id")) for d in (state.get("reranked") or [])[:3]]
        hits_want = [d.get("source_id") for d in state.get("reranked") or []].count(want)
        print(f"\n[Q] {q}")
        print(f"    reranked 상위 3 source: {top_sources}")
        print(f"    기대 회의 포함({want}): {hits_want > 0}")

        if errs:
            failures += 1
            print("    FAIL:")
            for e in errs:
                print(f"      - {e}")
        elif hits_want == 0:
            failures += 1
            print("    FAIL: 평가용 회의 source가 검색 결과에 없음(Day 11 회귀 이상 가능)")
        else:
            print("    PASS (citations ↔ reranked[:5] 정합 + 기대 source 포함)")

    if failures:
        print("\n[verify_streamlit_citation_alignment] 종료: 실패 있음", file=sys.stderr)
        return 1
    print("\n[verify_streamlit_citation_alignment] 전부 성공")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
