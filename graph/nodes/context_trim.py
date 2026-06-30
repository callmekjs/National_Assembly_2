from __future__ import annotations

import re

from graph.state import QAState
from service.speaker_aliases import extract_speaker_marker, normalize_speaker_name

_CHRONO_TYPES = {"comparison", "meeting_summary"}
_CHRONO_QUERY_RE = re.compile(
    r"날짜별|시기별|연도별|시간순|회의일순|흐름|변화|추이|경과|"
    r"논의(?:가|된|한|했|하|는|를)?\s*(?:있|되|나오|정리|요약)|"
    r"(?:있었|다뤘|언급됐|논의됐)(?:어|나|는지|나요|습니까)?|"
    r"(?:2024|2025|2026|최근|이전|과거|현재|부터|까지)"
)


def _quote_snippet(chunk_text: str, max_len: int = 160) -> str:
    """
    청크 앞부분이 발언 중간에서 끊기면 인용이 어색하다.
    앞쪽 짧은 구간에서 문장 끝을 찾아 그 이후부터 스니펫을 잡는다.
    """
    t = (chunk_text or "").replace("\r\n", "\n").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    for _ in range(2):
        if len(t) < 25:
            break
        head = t[:120]
        best_end: int | None = None
        for sep in (
            "습니다.",
            "입니다.",
            "였습니다.",
            "했습니다.",
            "니다.",
            "다.",
            "요.",
            "죠.",
            "네.",
            "음.",
            "어.",
            "。",
            "?",
            "!",
            "…",
        ):
            i = head.find(sep)
            if i != -1:
                end = i + len(sep)
                if end <= 60 and (best_end is None or end < best_end):
                    best_end = end
        if best_end is not None:
            t = t[best_end:].lstrip(" 　‧··•")
        else:
            break

    if len(t) <= max_len:
        return t
    cut = t[:max_len]
    for sep in (" ", ",", ".", "?", "!", "다", "요"):
        sp = cut.rfind(sep)
        if sp > int(max_len * 0.45):
            cut = cut[: sp + 1]
            break
    return cut.rstrip(" ,.;:，、") + "..."


def _speaker_from_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"\[발언자:\s*([^\]\n]+)\]", t)
    if m:
        return normalize_speaker_name(m.group(1).strip())
    detected_speaker, _, _ = extract_speaker_marker(t)
    if detected_speaker:
        return detected_speaker
    m = re.match(r"[○◯]\s*([가-힣A-Za-z0-9·ㆍ-]{2,20}(?:\s+[가-힣A-Za-z0-9·ㆍ-]{1,20})?)", t)
    return normalize_speaker_name(m.group(1).strip()) if m else ""


def _speaker_label(doc: dict) -> str:
    meta = doc.get("metadata") or {}
    speaker = str(doc.get("speaker") or meta.get("speaker") or "").strip()
    role = str(doc.get("speaker_role") or meta.get("speaker_role") or "").strip()
    detected_speaker, detected_role, _ = extract_speaker_marker(doc.get("chunk_text", "") or doc.get("content", ""))
    if detected_speaker:
        speaker = detected_speaker
        role = detected_role or role
    elif not speaker:
        speaker = _speaker_from_text(doc.get("chunk_text", "") or doc.get("content", ""))
    label = f"{speaker} {role}".strip() if (speaker and role and role not in speaker) else (speaker or role or "발언자 미상")
    party = str(doc.get("party") or meta.get("party") or "").strip()
    if party and party not in ("정부", "미확인", ""):
        label = f"{label} ({party})"
    elif str(doc.get("position_type") or meta.get("position_type") or "") == "정부측":
        label = f"{label} (정부측)"
    return label


def _build_chunk_with_context(doc: dict) -> str:
    """prev_context / next_context가 있으면 발언 전후를 함께 구성.
    발언자 헤더(정당 포함)를 앞에 붙여 LLM이 여당/야당/정부측을 파악할 수 있도록 한다.
    """
    meta = doc.get("metadata") or {}
    speaker = str(doc.get("speaker") or meta.get("speaker") or "").strip()
    role = str(doc.get("speaker_role") or meta.get("speaker_role") or "").strip()
    party = str(doc.get("party") or meta.get("party") or "").strip()
    position_type = str(doc.get("position_type") or meta.get("position_type") or "").strip()
    prev = (doc.get("prev_context") or "").strip()
    text = (doc.get("chunk_text") or "").strip()
    nxt = (doc.get("next_context") or "").strip()
    detected_speaker, detected_role, _ = extract_speaker_marker(text)
    if detected_speaker:
        speaker = detected_speaker
        role = detected_role or role
    elif not speaker:
        speaker = _speaker_from_text(text)

    # 발언자 헤더 구성 (party/position_type 포함)
    parts: list[str] = []
    if speaker or role:
        label = f"{speaker} {role}".strip() if (speaker and role) else (speaker or role)
        if party and party not in ("정부", "미확인", ""):
            label += f" ({party})"
        elif position_type == "정부측":
            label += " (정부측)"
        parts.append(f"[발언자: {label}]")

    if prev:
        parts.append(f"[이전 발언] {prev}")
    parts.append(text)
    if nxt:
        parts.append(f"[다음 발언] {nxt}")
    return "\n".join(parts)


def _parse_turn_index(doc: dict) -> int:
    meta = doc.get("metadata") or {}
    for value in (doc.get("turn_index"), meta.get("turn_index")):
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    chunk_id = str(doc.get("chunk_id") or meta.get("chunk_id") or "")
    matches = re.findall(r"\d+", chunk_id)
    return int(matches[-1]) if matches else 0


def _meeting_date(doc: dict) -> str:
    meta = doc.get("metadata") or {}
    return str(meta.get("meeting_date") or doc.get("date") or "9999-99-99")


def _should_sort_chronological(state: QAState) -> bool:
    meta = state.get("meta") or {}
    explicit = meta.get("citation_sort")
    if explicit in {"chronological", "relevance"}:
        return explicit == "chronological"

    question_type = str(meta.get("question_type") or "").strip()
    if question_type in _CHRONO_TYPES:
        return True

    question = str(state.get("question") or "")
    return bool(_CHRONO_QUERY_RE.search(question))


def _apply_citation_sort(state: QAState, docs: list[dict]) -> list[dict]:
    meta = state.setdefault("meta", {})
    if _should_sort_chronological(state):
        meta["citation_sort"] = "chronological"
        return sorted(
            docs,
            key=lambda d: (
                _meeting_date(d),
                str((d.get("metadata") or {}).get("committee") or ""),
                _parse_turn_index(d),
                str(d.get("chunk_id") or d.get("source_id") or ""),
            ),
        )
    meta["citation_sort"] = "relevance"
    return docs


def run(state: QAState) -> QAState:
    docs = state.get("reranked") or state.get("retrieved", [])
    docs = _apply_citation_sort(state, docs)
    if state.get("reranked"):
        state["reranked"] = docs
    elif state.get("retrieved"):
        state["retrieved"] = docs
    top_k = int((state.get("meta") or {}).get("top_k", 4))
    chunks = [f"[{i}]\n{_build_chunk_with_context(d)}" for i, d in enumerate(docs[:top_k], start=1)]
    state["context"] = "\n\n".join(chunks)[:7000]
    state["citations"] = []
    for d in docs[:top_k]:
        meta = d.get("metadata") or {}
        state["citations"].append(
            {
                "source_id": d.get("source_id", ""),
                "date": d.get("date", ""),
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "chunk_id": d.get("chunk_id", ""),
                "speaker": _speaker_label(d),
                "speaker_role": str(d.get("speaker_role") or meta.get("speaker_role") or "").strip(),
                "party": str(d.get("party") or meta.get("party") or "").strip(),
                "position_type": str(d.get("position_type") or meta.get("position_type") or "").strip(),
                "quote": _quote_snippet(d.get("chunk_text", "") or ""),
                "chunk_text": (d.get("chunk_text") or "").strip(),
                "source_path": str(meta.get("source_path") or "").strip(),
                "committee": str(meta.get("committee") or "").strip(),
                "page_no": meta.get("page_no"),
                "speaker_original": str(meta.get("speaker_original") or "").strip(),
            }
        )
    return state
