from __future__ import annotations

import logging
import os
import re
import time
from datetime import date

from graph.state import QAState
from service.llm.llm_client import chat, is_chat_failure_message
from service.llm.prompt_templates import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

_MAX_OUT = int(os.getenv("GENERATE_MAX_TOKENS", "512"))


def _est_tokens(text: str) -> int:
    """대략 토큰 수(출력 과다 방지용 요약 로그)."""
    return max(0, len(text) // 4)


def _sanitize_context(context: str) -> str:
    """시스템 지침을 제거하고 문서 내용만 추려낸다."""
    if not context:
        return ""

    snippet = context
    marker_pattern = re.compile(
        r"(##\s*관련\s*문서|참고\s*문서들:|DOCUMENTS:|관련 정보를 찾았습니다:)",
        flags=re.IGNORECASE,
    )
    match = marker_pattern.search(context)
    if match:
        snippet = context[match.end():]
    else:
        user_prompt_pattern = re.compile(r"(사용자 질문:|질문:)", flags=re.IGNORECASE)
        match_user = user_prompt_pattern.search(context)
        if match_user:
            snippet = context[match_user.end():]

    snippet = re.sub(r"당신은 도움이 되는.+?답변해주세요\.", " ", snippet, flags=re.DOTALL)
    snippet = re.sub(r"(사용자 질문:|질문:).+?(?=(\[문서|\bDOCUMENT|\Z))", " ", snippet, flags=re.DOTALL | re.IGNORECASE)
    snippet = re.sub(r"\s+", " ", snippet).strip()

    if not snippet:
        return ""

    sentences = re.split(r"(?<=\.)\s+|\n", snippet)
    cleaned_sentences = []
    for sent in sentences:
        text = sent.strip()
        if not text:
            continue
        cleaned_sentences.append(text)
        if len(cleaned_sentences) >= 3:
            break
    return " ".join(cleaned_sentences)


def _fallback_answer(question: str, context: str) -> str:
    """LLM이 비어 있는 답을 돌려줄 때 최소한의 안내 문구를 생성."""
    snippet = _sanitize_context(context)
    if snippet:
        preview = snippet[:600].strip()
        return (
            "죄송합니다. 모델이 답변을 생성하지 못했습니다. "
            "다음 참고 내용을 확인해 주세요:\n\n"
            "```markdown\n"
            f"{preview}\n"
            "```"
        )
    return (
        "죄송합니다. 현재 질문에 대한 답변을 생성하지 못했습니다. "
        "잠시 후 다시 시도해 주세요."
    )


def _build_numbered_context(state: QAState) -> str:
    """LLM에 전달할 문맥을 [n] 번호와 함께 구성한다. 답변에는 raw 메타 키(source= 등)를 노출하지 말라고 시스템에서 지시한다."""
    docs = state.get("reranked") or state.get("retrieved") or []
    sections: list[str] = []
    for idx, doc in enumerate(docs[:5], start=1):
        body = (doc.get("chunk_text") or "").strip()
        if not body:
            continue
        meta = doc.get("metadata") or {}
        speaker = str(meta.get("speaker") or "").strip() or "미상"
        date = doc.get("date") or "날짜 미상"
        sections.append(f"[{idx}] (회의일 {date}) 발언자: {speaker}\n{body}")
    return "\n\n".join(sections)


def _sanitize_invalid_citations(answer: str, max_ref: int) -> str:
    """존재하지 않는 인용 번호([n])를 제거한다."""
    if not answer or max_ref <= 0:
        return answer

    def _replace(match: re.Match[str]) -> str:
        ref_no = int(match.group(1))
        return match.group(0) if 1 <= ref_no <= max_ref else ""

    cleaned = re.sub(r"\[(\d+)\]", _replace, answer)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def build_prompts_from_state(state: QAState) -> tuple[str, str]:
    """스트리밍 생성 시 chat.py에서 직접 사용할 (system_prompt, user_prompt) 반환."""
    question = state.get("question", "")
    committee = str(state.get("meta", {}).get("committee") or "").strip()
    context = _build_numbered_context(state) or state.get("context", "")
    doc_name_query = bool(state.get("meta", {}).get("doc_name_query"))
    return build_system_prompt(question, committee=committee), build_user_prompt(
        question, context, reference_date=date.today(), doc_name_query=doc_name_query
    )


def run(state: QAState) -> QAState:
    """
    역할:
      - QAState의 question, context 등으로 시스템/유저 프롬프트를 생성
      - LLM(Chat)으로 답변 초안 생성 → state["draft_answer"]에 저장

    동작 흐름:
      1. state에서 질문, 컨텍스트 추출
      2. 시스템 프롬프트(페르소나·규칙·질문별 강조)와 유저 프롬프트(질문+문맥)를 생성
      3. chat() 함수 호출로 답변 텍스트 생성
      4. 생성된 답변을 state["draft_answer"]에 저장
      5. 예외 발생시 에러로그 남기고 안내 문구 반환

    Args:
        state (QAState): LangGraph에서 전달받은 워크플로 상태 딕셔너리

    Returns:
        QAState: draft_answer가 추가된 상태
    """
    state.pop("llm_error_kind", None)
    state.pop("generation_skipped", None)

    # 스트리밍 모드: chat.py가 직접 생성하므로 여기선 스킵
    if state.get("meta", {}).get("skip_generate"):
        state["draft_answer"] = ""
        state["generation_skipped"] = "streaming"
        logger.info("[Generate] skipped: streaming mode")
        return state

    if state.get("retrieval_empty"):
        state["draft_answer"] = ""
        state["generation_skipped"] = "no_hits"
        logger.info("[Generate] skipped: retrieval_empty")
        return state

    try:
        question = state.get("question", "")
        committee = str(state.get("meta", {}).get("committee") or "").strip()
        docs = state.get("reranked") or state.get("retrieved") or []
        context = _build_numbered_context(state) or state.get("context", "")
        max_ref = len(docs)

        doc_name_query = bool((state.get("meta") or {}).get("doc_name_query"))
        system_prompt = build_system_prompt(question, committee=committee)
        user_prompt = build_user_prompt(question, context, reference_date=date.today(), doc_name_query=doc_name_query)
        prompt_blob = f"{system_prompt}\n{user_prompt}"

        t0 = time.perf_counter()
        answer = chat(
            system=system_prompt,
            user=user_prompt,
            max_tokens=_MAX_OUT,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if is_chat_failure_message(answer):
            state["llm_error_kind"] = "model_backend"
            state["draft_answer"] = answer.strip()
            logger.info(
                "[Generate] model_backend chars=%s ms=%s",
                len(answer),
                elapsed_ms,
            )
            return state

        answer = _sanitize_invalid_citations(answer, max_ref)
        state["draft_answer"] = answer

        logger.info(
            "[Generate] ok ms=%s prompt_est_tok=%s out_est_tok=%s out_chars=%s",
            elapsed_ms,
            _est_tokens(prompt_blob),
            _est_tokens(answer),
            len(answer),
        )

        if not answer.strip():
            fallback = _fallback_answer(question, context)
            state["draft_answer"] = fallback
            logger.info("[Generate] empty answer → fallback chars=%s", len(fallback))
    except Exception as exc:
        logger.exception("[Generate] exception")
        state["llm_error_kind"] = "exception"
        state["draft_answer"] = "죄송합니다. 답변 생성 중 오류가 발생했습니다."

    return state
