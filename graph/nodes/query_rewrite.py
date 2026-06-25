from __future__ import annotations

import re
import logging

from graph.state import QAState

logger = logging.getLogger(__name__)

_QUESTION_ENDINGS = re.compile(
    r'\s*(?:인가요?|인지요?|나요?|어요?|해요?|죠?|할까요?|하나요?|있나요?|없나요?|'
    r'이에요?|예요?|뭐야|뭔가|알려줘|해줘|주세요|인가|인지요?|ㄴ가요|ㄹ까요|'
    r'누구야|누구인가요?|어떻게 생각해|어떤가요?|어떤지)\??$',
    re.UNICODE,
)

_ABBREV = [
    ('민주당', '더불어민주당'),
    ('국힘', '국민의힘'),
    ('한동훈 당', '국민의힘'),
]


def _normalize(question: str) -> str:
    q = _QUESTION_ENDINGS.sub('', question).strip()
    for abbr, full in _ABBREV:
        q = q.replace(abbr, full)
    return q if len(q) >= 4 else question


def run(state: QAState) -> QAState:
    question = (state.get("question") or "").strip()
    if not question:
        state["rewritten_query"] = question
        return state

    rewritten = _normalize(question)
    state["rewritten_query"] = rewritten

    if rewritten != question:
        logger.info("[QueryRewrite] %r → %r", question, rewritten)
    return state
