from __future__ import annotations

import logging
import os

from graph.state import QAState
from service.llm.llm_client import chat

logger = logging.getLogger(__name__)

_SYSTEM = (
    "너는 국회 회의록 검색 전문가다. "
    "사용자의 질문을 벡터 검색과 키워드 검색에 최적화된 한국어 쿼리로 변환한다.\n\n"
    "규칙:\n"
    "- 질문 형태(~가요, ~어요, ~어, ~인가요, ~할까요)를 제거하고 핵심 명사·동사 중심으로 재구성한다.\n"
    "- 고유명사(인물명, 정당명, 부처명, 법안명)는 그대로 유지한다.\n"
    "- 줄임말은 원래 표현으로 확장한다 (예: 민주당 → 더불어민주당).\n"
    "- 여야 비교 질문이면 양쪽 정당명을 모두 포함한다.\n"
    "- 재작성 결과만 출력한다. 설명·부연·따옴표 없이 쿼리 문자열만 한 줄로 출력한다.\n"
    "- 원본 질문이 이미 키워드 형태면 그대로 반환한다."
)


def _rewrite(question: str) -> str:
    try:
        result = chat(
            system=_SYSTEM,
            user=f"질문: {question}",
            max_tokens=80,
        )
        rewritten = result.strip().strip('"').strip("'")
        if rewritten and len(rewritten) >= 4:
            return rewritten
    except Exception as exc:
        logger.warning("[QueryRewrite] LLM 실패, 원본 사용: %s", exc)
    return question


def run(state: QAState) -> QAState:
    question = (state.get("question") or "").strip()
    if not question:
        state["rewritten_query"] = question
        return state

    rewritten = _rewrite(question)
    state["rewritten_query"] = rewritten

    if rewritten != question:
        logger.info("[QueryRewrite] %r → %r", question, rewritten)
    else:
        logger.info("[QueryRewrite] 변경 없음: %r", question)

    return state
