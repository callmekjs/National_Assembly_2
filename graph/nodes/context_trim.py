from __future__ import annotations

import re

from graph.state import QAState


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
        return m.group(1).strip()
    m = re.match(r"[○◯]\s*([가-힣A-Za-z0-9·ㆍ-]{2,20}(?:\s+[가-힣A-Za-z0-9·ㆍ-]{1,20})?)", t)
    return m.group(1).strip() if m else ""


def _speaker_label(doc: dict) -> str:
    meta = doc.get("metadata") or {}
    speaker = str(doc.get("speaker") or meta.get("speaker") or "").strip()
    role = str(doc.get("speaker_role") or meta.get("speaker_role") or "").strip()
    if not speaker:
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
    speaker = (doc.get("speaker") or "").strip()
    role = (doc.get("speaker_role") or "").strip()
    party = (doc.get("party") or "").strip()
    position_type = (doc.get("position_type") or "").strip()
    prev = (doc.get("prev_context") or "").strip()
    text = (doc.get("chunk_text") or "").strip()
    nxt = (doc.get("next_context") or "").strip()

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


def run(state: QAState) -> QAState:
    docs = state.get("reranked") or state.get("retrieved", [])
    state["context"] = "\n\n".join(_build_chunk_with_context(d) for d in docs[:8])[:12000]
    state["citations"] = []
    for d in docs[:8]:
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
            }
        )
    return state
