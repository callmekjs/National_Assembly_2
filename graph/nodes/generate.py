from __future__ import annotations

import logging
import os
import re
import time
from datetime import date

from graph.state import QAState
from service.llm.llm_client import chat, get_last_usage, is_chat_failure_message
from service.llm.prompt_templates import build_system_prompt, build_user_prompt, needs_reasoning_model, _is_existence_query

logger = logging.getLogger(__name__)

_MAX_OUT = int(os.getenv("GENERATE_MAX_TOKENS", "1024"))
_REASONING_MODEL = os.getenv("OPENAI_REASONING_MODEL", "gpt-4o")

_VERIFIER_SYSTEM = (
    "너는 팩트체커다. 아래 [질문]의 전제(특정 발언·사실·합의·논의)가 "
    "[컨텍스트]에 그 내용 그대로 직접 존재하는지 판단한다.\n"
    "판단 기준:\n"
    "- 질문이 전제하는 그 발언·사실이 [컨텍스트]에 명시적으로 등장하면 → CONFIRMED\n"
    "- 유사한 주제가 있어도 질문의 전제 그 내용이 없으면 → NOT_CONFIRMED\n"
    "- 애매하거나 불분명하면 → NOT_CONFIRMED\n"
    "반드시 첫 줄에 CONFIRMED 또는 NOT_CONFIRMED 중 하나만 출력한다. "
    "설명·부연 금지."
)

_REFUSAL_ANSWER = "회의록에서 해당 내용은 확인되지 않았습니다."


def _verify_claim(question: str, context: str) -> bool:
    """존재 여부 질문의 전제가 컨텍스트에 실제로 있는지 확인. True=존재.
    생성 모델과 무관하게 항상 추론 능력이 강한 모델을 사용한다."""
    try:
        result = chat(
            system=_VERIFIER_SYSTEM,
            user=f"[질문]\n{question}\n\n[컨텍스트]\n{context[:2500]}",
            max_tokens=20,
            model=_REASONING_MODEL,
        )
        return "CONFIRMED" in (result or "").upper() and "NOT_CONFIRMED" not in (result or "").upper()
    except Exception:
        return True  # 검증 실패 시 안전하게 생성 진행


def _est_tokens(text: str) -> int:
    """대략 토큰 수(출력 과다 방지용 요약 로그). 한국어 기준 글자당 ~0.5토큰."""
    return max(0, len(text) // 2)


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


_MAX_CONTEXT_DOCS = int(os.getenv("MAX_CONTEXT_DOCS", "8"))


def _build_numbered_context(state: QAState) -> str:
    """LLM에 전달할 문맥을 [n] 번호와 함께 구성한다. 답변에는 raw 메타 키(source= 등)를 노출하지 말라고 시스템에서 지시한다."""
    docs = state.get("reranked") or state.get("retrieved") or []
    top_k = min(int((state.get("meta") or {}).get("top_k", 6)), _MAX_CONTEXT_DOCS)
    sections: list[str] = []
    for idx, doc in enumerate(docs[:top_k], start=1):
        body = (doc.get("chunk_text") or "").strip()
        if not body:
            continue
        meta = doc.get("metadata") or {}
        speaker_raw = doc.get("speaker") or meta.get("speaker") or ""
        role_raw = doc.get("speaker_role") or meta.get("speaker_role") or ""
        party = doc.get("party") or meta.get("party") or ""
        position_type = doc.get("position_type") or meta.get("position_type") or ""

        speaker_label = f"{speaker_raw} {role_raw}".strip() if role_raw else speaker_raw
        if party and party not in ("정부", "미확인", ""):
            speaker_label += f" ({party})"
        elif position_type == "정부측":
            speaker_label += " (정부측)"
        speaker = speaker_label or "미상"
        date_str = doc.get("date") or "날짜 미상"

        prev = (doc.get("prev_context") or "").strip()
        nxt = (doc.get("next_context") or "").strip()
        parts: list[str] = []
        if prev:
            parts.append(f"[이전 발언] {prev}")
        parts.append(body)
        if nxt:
            parts.append(f"[다음 발언] {nxt}")

        sections.append(f"[{idx}] (회의일 {date_str}) 발언자: {speaker}\n" + "\n".join(parts))
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
    question_type = str(state.get("meta", {}).get("question_type") or "").strip()
    context = _build_numbered_context(state) or state.get("context", "")
    doc_name_query = bool(state.get("meta", {}).get("doc_name_query"))
    return build_system_prompt(question, committee=committee, question_type=question_type), build_user_prompt(
        question,
        context,
        reference_date=date.today(),
        doc_name_query=doc_name_query,
        question_type=question_type,
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

    # 애매한 쿼리 — 명확화 메시지를 답변으로 반환
    if state.get("meta", {}).get("needs_clarification"):
        msg = state.get("meta", {}).get("clarification_message", "질문을 더 구체적으로 입력해 주세요.")
        state["draft_answer"] = msg
        state["generation_skipped"] = "needs_clarification"
        logger.info("[Generate] skipped: needs_clarification")
        return state

    # 스트리밍 모드: chat.py가 직접 생성하므로 여기선 스킵
    if state.get("meta", {}).get("skip_generate"):
        state["draft_answer"] = ""
        state["generation_skipped"] = "streaming"
        logger.info("[Generate] skipped: streaming mode")
        return state

    if state.get("retrieval_empty"):
        question = state.get("question", "")
        committee = str((state.get("meta") or {}).get("committee") or "").strip()
        scope = f"{committee} " if committee else "전체 위원회 "
        state["draft_answer"] = (
            f"죄송합니다. 질문 \"{question}\"에 해당하는 회의록을 찾을 수 없습니다.\n\n"
            f"{scope}회의록에 관련 내용이 없거나, "
            "질문하신 날짜·인물·주제가 보유 회의록 범위 밖일 수 있습니다. "
            "다른 표현으로 다시 질문해 주세요."
        )
        state["generation_skipped"] = "no_hits"
        logger.info("[Generate] skipped: retrieval_empty → 안내 문구 반환")
        return state

    try:
        question = state.get("question", "")
        committee = str(state.get("meta", {}).get("committee") or "").strip()
        docs = state.get("reranked") or state.get("retrieved") or []
        context = _build_numbered_context(state) or state.get("context", "")
        max_ref = len(docs)

        # 존재 여부 질문: 전제 검증 먼저 — 없으면 생성 스킵
        if _is_existence_query(question):
            if not _verify_claim(question, context):
                state["draft_answer"] = _REFUSAL_ANSWER
                state["generation_skipped"] = "existence_not_confirmed"
                logger.info("[Generate] existence check: NOT_CONFIRMED → 거절 반환")
                return state

        doc_name_query = bool((state.get("meta") or {}).get("doc_name_query"))
        question_type = str((state.get("meta") or {}).get("question_type") or "").strip()
        system_prompt = build_system_prompt(question, committee=committee, question_type=question_type)
        user_prompt = build_user_prompt(
            question,
            context,
            reference_date=date.today(),
            doc_name_query=doc_name_query,
            question_type=question_type,
        )
        prompt_blob = f"{system_prompt}\n{user_prompt}"

        _model = _REASONING_MODEL if needs_reasoning_model(question) else None
        t0 = time.perf_counter()
        answer = chat(
            system=system_prompt,
            user=user_prompt,
            max_tokens=_MAX_OUT,
            model=_model,
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

        latency = state.get("latency_ms") or {}
        latency["generate_ms"] = round(elapsed_ms, 1)
        usage = get_last_usage()
        if usage.get("total_tokens"):
            latency["prompt_tokens"] = usage["prompt_tokens"]
            latency["completion_tokens"] = usage["completion_tokens"]
            latency["total_tokens"] = usage["total_tokens"]
        state["latency_ms"] = latency

        logger.info(
            "[Generate] ok ms=%s prompt_tok=%s completion_tok=%s total_tok=%s out_chars=%s",
            elapsed_ms,
            usage.get("prompt_tokens", _est_tokens(prompt_blob)),
            usage.get("completion_tokens", _est_tokens(answer)),
            usage.get("total_tokens", "est"),
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
