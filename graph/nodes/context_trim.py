from __future__ import annotations

import re

from graph.state import QAState


def _quote_snippet(chunk_text: str, max_len: int = 200) -> str:
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


def run(state: QAState) -> QAState:
    docs = state.get("reranked") or state.get("retrieved", [])
    state["context"] = "\n\n".join((d.get("chunk_text") or "") for d in docs[:5])[:8000]
    state["citations"] = []
    for d in docs[:5]:
        meta = d.get("metadata") or {}
        sp = str(meta.get("speaker") or "").strip()
        state["citations"].append(
            {
                "source_id": d.get("source_id", ""),
                "date": d.get("date", ""),
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "chunk_id": d.get("chunk_id", ""),
                "speaker": sp or "발언자 미상",
                "quote": _quote_snippet(d.get("chunk_text", "") or ""),
            }
        )
    return state
