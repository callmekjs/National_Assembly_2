from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TURNS_DIR = ROOT / "data" / "v2" / "transform" / "turns"
CHUNKS_DIR = ROOT / "data" / "v2" / "transform" / "chunks"
OUT_DIR = ROOT / "data" / "v2" / "transform" / "final"

MIN_CHARS = 300
MAX_CHARS = 600
SKIP_CHARS = 30
CONTEXT_CHARS = 100  # prev/next context window

# 정부측 자동 감지 키워드 (speaker_role에 포함되면 정부측으로 분류)
_GOVT_ROLE_KEYWORDS = {
    "장관", "차관", "차장", "청장", "국장", "실장", "본부장",
    "대사", "과장", "조정관", "대변인", "비서관",
}


def _load_speaker_table() -> dict[str, str]:
    """speakers.json → {이름: 정당} 역색인"""
    path = ROOT / "data" / "speakers.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    result: dict[str, str] = {}
    for party, names in raw.items():
        for name in names:
            result[name] = party
    return result


_SPEAKER_TABLE: dict[str, str] = _load_speaker_table()


def _enrich_speaker_metadata(meta: dict, speaker: str, speaker_role: str) -> None:
    """party, position_type을 meta에 in-place 추가."""
    # 후보자 (인사청문회)
    if speaker == "후보자":
        meta["party"] = "정부"
        meta["position_type"] = "후보자"
        return

    # 정부측 자동 감지
    for kw in _GOVT_ROLE_KEYWORDS:
        if kw in speaker_role:
            meta["party"] = "정부"
            meta["position_type"] = "정부측"
            return

    # 전문위원
    if "전문위원" in speaker_role:
        meta["party"] = ""
        meta["position_type"] = "전문위원"
        return

    # 위원장 / 소위원장
    if "위원장" in speaker_role:
        meta["party"] = _SPEAKER_TABLE.get(speaker, "미확인")
        meta["position_type"] = "위원장"
        return

    # 일반 위원 (국회의원)
    if "위원" in speaker_role:
        meta["party"] = _SPEAKER_TABLE.get(speaker, "미확인")
        meta["position_type"] = "의원"
        return

    # 기타 (발언자 미상, 이름 없음 등)
    meta["party"] = _SPEAKER_TABLE.get(speaker, "")
    meta["position_type"] = "기타"


def _count_tokens(text: str) -> int:
    """토큰 수 추정. tiktoken 미설치 시 글자 수 // 2로 폴백 (한국어 기준)."""
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 2)


def _make_chunk_id(turn: dict) -> str:
    return f"{turn['source_id']}_turn_{turn['turn_index']:04d}"


def _make_embed_text(turn: dict) -> str:
    meta = turn.get("metadata", {})
    date = meta.get("meeting_date", "")
    committee = meta.get("committee", "")
    speaker = turn.get("speaker", "")
    role = turn.get("speaker_role", "")
    party = meta.get("party", "")
    position_type = meta.get("position_type", "")

    speaker_label = f"{speaker} {role}".strip() if role else speaker

    # 정당 또는 소속 표시 (embed semantic search 향상)
    if party and party not in ("정부", "미확인", ""):
        party_label = f" ({party})"
    elif position_type == "정부측":
        party_label = " (정부측)"
    elif position_type == "후보자":
        party_label = " (정부 후보자)"
    else:
        party_label = ""

    if speaker_label and party_label:
        speaker_label = f"{speaker_label}{party_label}"

    parts: list[str] = []
    if date:
        parts.append(f"[회의일: {date}]")
    if committee:
        parts.append(f"[위원회: {committee}]")
    if speaker_label:
        parts.append(f"[발언자: {speaker_label}]")

    prefix = " ".join(parts)
    body = turn.get("clean_text", "")
    return f"{prefix}\n{body}".strip() if prefix else body


def _merge_turns(turns: list[dict]) -> list[dict]:
    if not turns:
        return []
    merged: list[dict] = []
    buf = dict(turns[0])
    for t in turns[1:]:
        same = (
            t["source_id"] == buf["source_id"]
            and t["speaker"] == buf["speaker"]
        )
        buf_len = len(buf.get("clean_text", ""))
        t_len = len(t.get("clean_text", ""))
        can_merge = same and buf_len < MIN_CHARS and (buf_len + t_len) <= MAX_CHARS
        if can_merge:
            buf["clean_text"] = buf["clean_text"].rstrip() + " " + t["clean_text"].lstrip()
        else:
            merged.append(buf)
            buf = dict(t)
    merged.append(buf)
    return merged


def _build_record(chunk: dict, source_id: str) -> dict:
    text = chunk.get("clean_text", "")
    token_count = _count_tokens(text)
    meta = dict(chunk.get("metadata", {}))
    meta["token_count"] = token_count  # metadata JSONB에 포함해야 DB에 저장됨

    speaker = chunk.get("speaker", "")
    speaker_role = chunk.get("speaker_role", "")
    _enrich_speaker_metadata(meta, speaker, speaker_role)

    # embed_text는 party/position_type이 채워진 meta로 생성
    enriched_chunk = {**chunk, "metadata": meta}
    return {
        "chunk_id": _make_chunk_id(chunk),
        "source_id": source_id,
        "page_no": chunk.get("page_no"),
        "turn_index": chunk.get("turn_index"),
        "speaker": speaker,
        "speaker_role": speaker_role,
        "section_type": chunk.get("section_type", "body"),
        "raw_text": text,
        "clean_text": text,
        "embed_text": _make_embed_text(enriched_chunk),
        "metadata": meta,
        "token_count": token_count,
    }


def _add_context_window(records: list[dict]) -> list[dict]:
    """각 청크 metadata에 인접 발언 앞 100자를 prev_context / next_context로 추가."""
    for i, rec in enumerate(records):
        if i > 0:
            rec["metadata"]["prev_context"] = records[i - 1]["clean_text"][:CONTEXT_CHARS]
        if i < len(records) - 1:
            rec["metadata"]["next_context"] = records[i + 1]["clean_text"][:CONTEXT_CHARS]
    return records


def main() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    final_path = OUT_DIR / "chunks_v2.jsonl"

    total = 0
    short_count = 0

    with final_path.open("w", encoding="utf-8") as final_out:
        for turns_path in sorted(TURNS_DIR.glob("*/turns.jsonl")):
            sid = turns_path.parent.name
            turns = []
            with turns_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        turns.append(json.loads(line))

            turns = [t for t in turns if len(t.get("clean_text", "")) >= SKIP_CHARS]
            records = [_build_record(c, sid) for c in _merge_turns(turns)]
            records = _add_context_window(records)

            src_out = CHUNKS_DIR / sid
            src_out.mkdir(parents=True, exist_ok=True)
            with (src_out / "chunks.jsonl").open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    final_out.write(json.dumps(r, ensure_ascii=False) + "\n")
                    total += 1
                    if len(r["clean_text"]) < 300:
                        short_count += 1

    ratio = short_count / max(total, 1)
    print(f"[chunker_v2] chunks={total} 300자미만={short_count}({ratio:.1%})")
    print(f"  → {CHUNKS_DIR}/{{source_id}}/chunks.jsonl")
    print(f"  → {final_path} (merged)")


if __name__ == "__main__":
    main()
