from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHUNKS_FINAL = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"
OUT_DIR       = ROOT / "data" / "v2" / "transform" / "qa_pairs"
OUT_FILE      = OUT_DIR / "qa_pairs_v2.jsonl"

MAX_GAP = 8  # turn_index 갭이 이보다 크면 Q-A 연결 단절로 간주
CONFIDENCE_THRESHOLD = 0.5  # 이 미만인 question은 statement로 처리


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 2)


def _concat_texts(turns: list[dict]) -> str:
    parts = []
    for t in turns:
        speaker = t.get("speaker", "")
        text    = (t.get("clean_text") or "").strip()
        parts.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(parts)


def _make_clean_text(q_group: list[dict], a_group: list[dict]) -> str:
    return f"[질의]\n{_concat_texts(q_group)}\n\n[답변]\n{_concat_texts(a_group)}"


def _make_embed_text(q_group: list[dict], a_group: list[dict]) -> str:
    meta = q_group[0].get("metadata", {})
    date      = meta.get("meeting_date", "")
    committee = meta.get("committee", "")
    q_speaker = q_group[0].get("speaker", "")
    q_role    = q_group[0].get("speaker_role", "")
    a_speaker = a_group[0].get("speaker", "")
    a_role    = a_group[0].get("speaker_role", "")
    q_party   = meta.get("party", "")

    q_label = f"{q_speaker} {q_role}".strip()
    if q_party and q_party not in ("정부", "미확인", ""):
        q_label += f" ({q_party})"
    a_label = f"{a_speaker} {a_role}".strip()

    header_parts = []
    if date:
        header_parts.append(f"[회의일: {date}]")
    if committee:
        header_parts.append(f"[위원회: {committee}]")
    if q_label:
        header_parts.append(f"[질의자: {q_label}]")
    if a_label:
        header_parts.append(f"[답변자: {a_label}]")
    header_parts.append("[발화유형: 질의-답변 쌍]")

    header = " ".join(header_parts)
    body   = _make_clean_text(q_group, a_group)
    return f"{header}\n{body}".strip()


def _make_qa_record(
    source_id: str,
    pair_index: int,
    q_group: list[dict],
    a_group: list[dict],
) -> dict:
    q0   = q_group[0]
    a0   = a_group[0]
    meta = dict(q0.get("metadata", {}))

    clean = _make_clean_text(q_group, a_group)
    embed = _make_embed_text(q_group, a_group)

    q_speaker = q0.get("speaker", "")
    q_role    = q0.get("speaker_role", "")
    a_speaker = a0.get("speaker", "")
    a_role    = a0.get("speaker_role", "")

    meta.update({
        "chunk_type":            "qa_pair",
        "utterance_type":        "qa_pair",
        "question_speaker":      q_speaker,
        "question_role":         q_role,
        "answer_speaker":        a_speaker,
        "answer_role":           a_role,
        "question_turn_indices": [t["turn_index"] for t in q_group],
        "answer_turn_indices":   [t["turn_index"] for t in a_group],
        "question_type_hints":   ["qa_pair_extract", "topic_search",
                                  "source_check", "report_generation"],
        "token_count":           _count_tokens(clean),
    })

    return {
        "chunk_id":    f"{source_id}_qa_{pair_index:04d}",
        "source_id":   source_id,
        "page_no":     q0.get("page_no"),
        "turn_index":  q0.get("turn_index"),
        "section_type": "body",
        "speaker":      f"{q_speaker} → {a_speaker}",
        "speaker_role": f"{q_role} → {a_role}",
        "raw_text":     clean,
        "clean_text":   clean,
        "embed_text":   embed,
        "metadata":     meta,
    }


def pair_qa_chunks(chunks: list[dict]) -> list[dict]:
    """
    청크 목록(단일 source_id 가정)을 순차 스캔해 Q-A 쌍 레코드를 반환한다.
    여러 source_id가 섞인 경우에도 source_id 경계를 자동으로 감지해 처리한다.
    """
    if not chunks:
        return []

    # source_id별 그룹 분리
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id", "")
        groups.setdefault(sid, []).append(c)

    all_pairs: list[dict] = []
    for sid, sid_chunks in groups.items():
        sid_chunks = sorted(sid_chunks, key=lambda c: c.get("turn_index", 0))
        all_pairs.extend(_pair_single_source(sid, sid_chunks))

    return all_pairs


def _pair_single_source(source_id: str, chunks: list[dict]) -> list[dict]:
    # qa_pair 레코드는 처리에서 제외 (재실행 시 중복 방지)
    utterance_chunks = [
        c for c in chunks
        if c.get("metadata", {}).get("chunk_type", "utterance") == "utterance"
    ]

    pairs: list[dict] = []
    pair_index = 0

    q_group: list[dict] = []
    a_group: list[dict] = []
    state = "IDLE"   # IDLE | QUESTIONING | ANSWERING

    def _emit() -> None:
        nonlocal pair_index
        if q_group and a_group:
            pairs.append(_make_qa_record(source_id, pair_index, q_group[:], a_group[:]))
            pair_index += 1

    def _gap(prev: dict | None, curr: dict) -> int:
        if prev is None:
            return 0
        return abs(curr.get("turn_index", 0) - prev.get("turn_index", 0))

    prev_chunk: dict | None = None

    for chunk in utterance_chunks:
        meta = chunk.get("metadata", {})
        utterance_type = meta.get("utterance_type", "statement")
        confidence = float(meta.get("utterance_type_confidence", 1.0))
        if utterance_type == "question" and confidence < CONFIDENCE_THRESHOLD:
            utterance_type = "statement"
        gap = _gap(prev_chunk, chunk)

        # ── 갭 초과 처리 ────────────────────────────────────────────
        if gap > MAX_GAP and state != "IDLE":
            if state == "ANSWERING":
                _emit()
            # QUESTIONING이면 답변 없는 질의 → 폐기
            q_group.clear()
            a_group.clear()
            state = "IDLE"

        # ── 상태 전환 ────────────────────────────────────────────────
        if state == "IDLE":
            if utterance_type == "question":
                q_group = [chunk]
                state = "QUESTIONING"

        elif state == "QUESTIONING":
            if utterance_type == "question":
                q_group.append(chunk)
            elif utterance_type == "answer":
                a_group = [chunk]
                state = "ANSWERING"
            elif utterance_type == "procedural":
                # 답변 없는 질의 — 폐기
                q_group.clear()
                state = "IDLE"

        elif state == "ANSWERING":
            if utterance_type == "answer":
                a_group.append(chunk)
            elif utterance_type == "question":
                _emit()
                q_group = [chunk]
                a_group = []
                state = "QUESTIONING"
            elif utterance_type == "procedural":
                _emit()
                q_group.clear()
                a_group.clear()
                state = "IDLE"

        prev_chunk = chunk

    # 마지막 쌍 처리
    if state == "ANSWERING":
        _emit()

    return pairs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []
    if not CHUNKS_FINAL.exists():
        print(f"[qa_pairer_v2] 청크 파일 없음: {CHUNKS_FINAL}")
        return

    with CHUNKS_FINAL.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_chunks.append(json.loads(line))

    pairs = pair_qa_chunks(all_chunks)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"[qa_pairer_v2] qa_pairs={len(pairs)} → {OUT_FILE}")


if __name__ == "__main__":
    main()
