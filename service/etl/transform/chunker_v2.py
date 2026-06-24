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


def _make_chunk_id(turn: dict) -> str:
    return f"{turn['source_id']}_turn_{turn['turn_index']:04d}"


def _make_embed_text(turn: dict) -> str:
    meta = turn.get("metadata", {})
    date = meta.get("meeting_date", "")
    committee = meta.get("committee", "")
    speaker = turn.get("speaker", "")
    role = turn.get("speaker_role", "")
    speaker_label = f"{speaker} {role}".strip() if role else speaker

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
    return {
        "chunk_id": _make_chunk_id(chunk),
        "source_id": source_id,
        "page_no": chunk.get("page_no"),
        "turn_index": chunk.get("turn_index"),
        "speaker": chunk.get("speaker", ""),
        "speaker_role": chunk.get("speaker_role", ""),
        "section_type": chunk.get("section_type", "body"),
        "raw_text": text,
        "clean_text": text,
        "embed_text": _make_embed_text(chunk),
        "metadata": chunk.get("metadata", {}),
    }


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
