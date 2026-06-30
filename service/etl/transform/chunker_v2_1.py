"""v2.1 chunker: section_type 세분화, 병합 추적, 해시, provenance 생성.

입력  : data/v2/transform/turns/{source_id}/turns.jsonl
출력  : data/v2/transform/final/chunks_v2_1.jsonl
        data/v2/transform/chunks_v2_1/{source_id}/chunks.jsonl
        data/v2/reports/provenance.jsonl
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from service.speaker_aliases import has_hanja, normalize_speaker_name
from service.etl.transform.chunker_v2 import (
    _add_context_window,
    _count_tokens,
    _enrich_question_type_metadata,
    _enrich_speaker_metadata,
    _make_embed_text,
)

ROOT = Path(__file__).resolve().parents[3]
TURNS_DIR = ROOT / "data" / "v2" / "transform" / "turns"
CHUNKS_DIR = ROOT / "data" / "v2" / "transform" / "chunks_v2_1"
OUT_DIR = ROOT / "data" / "v2" / "transform" / "final"
REPORTS_DIR = ROOT / "data" / "v2" / "reports"

MIN_CHARS = 300
MAX_CHARS = 600
LOW_SIGNAL_CHARS = 30
CONTEXT_CHARS = 100

# --- section_type 분류 패턴 ---

_COVER_RE = re.compile(r"제\d+회[-–]|국회사무처|의사국|회의록\s*제\d+호")
_AGENDA_RE = re.compile(
    r"의\s*사\s*일\s*정|상\s*정\s*안\s*건|심\s*의\s*안\s*건|회\s*의\s*안\s*건"
    r"|일\s*정\s*제\s*\d+\s*항|안건\s*제\s*\d+\s*호"
)
_PROCEDURAL_RE = re.compile(
    r"개의를?\s*선언|산회를?\s*선언|정회를?\s*선언|속개합니다|속개를?\s*선언"
    r"|회의에?\s*들어가겠습니다|회의를?\s*(마치겠습니다|마칩니다|폐회)"
    r"|다음\s*안건으로\s*넘어|잠깐\s*정회|회의\s*시작|회의를?\s*시작"
)
_APPENDIX_RE = re.compile(r"붙\s*임\s*\d*\s*[\.．]|보\s*고\s*사\s*항|별\s*첨|첨부\s*자료")

_LOW_SIGNAL_TOKENS = frozenset({
    "예", "네", "아니요", "아니오", "알겠습니다", "감사합니다",
    "수고하셨습니다", "이상입니다", "그렇습니다", "맞습니다",
})


def classify_section_type(speaker: str, text: str) -> str:
    t = text.strip()
    if not speaker:
        if _AGENDA_RE.search(t):
            return "agenda"
        if _APPENDIX_RE.search(t):
            return "appendix"
        if _COVER_RE.search(t):
            return "cover"
        return "cover"
    if _PROCEDURAL_RE.search(t):
        return "procedural"
    if _AGENDA_RE.search(t):
        return "agenda"
    if _APPENDIX_RE.search(t):
        return "appendix"
    return "body"


def is_low_signal(text: str) -> bool:
    t = text.strip()
    if len(t) >= LOW_SIGNAL_CHARS:
        return False
    return any(tok in t for tok in _LOW_SIGNAL_TOKENS) or len(t) < 10


def _sha256(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def compute_doc_hash(source_id: str, meeting_date: str, committee: str, texts: list[str]) -> str:
    return _sha256(source_id, meeting_date, committee, "\n".join(texts))


def compute_chunk_hash(
    chunk_id: str,
    speaker: str,
    speaker_role: str,
    turn_index: int,
    clean_text: str,
    section_type: str,
) -> str:
    return _sha256(chunk_id, speaker, speaker_role, str(turn_index), clean_text, section_type)


def merge_turns_v2_1(turns: list[dict]) -> list[dict]:
    """동일 speaker의 짧은 body turns를 병합하고 추적 메타를 기록."""
    if not turns:
        return []
    merged: list[dict] = []
    buf = dict(turns[0])
    buf["_merged_turn_indices"] = [turns[0]["turn_index"]]
    buf["_merged_from_chunk_ids"] = [
        f"{turns[0]['source_id']}_turn_{turns[0]['turn_index']:04d}"
    ]

    for t in turns[1:]:
        buf_sec = buf.get("section_type", "body")
        t_sec = t.get("section_type", "body")
        same_source = t["source_id"] == buf["source_id"]
        same_speaker = bool(t["speaker"]) and t["speaker"] == buf["speaker"]
        both_body = buf_sec == "body" and t_sec == "body"
        buf_len = len(buf.get("clean_text", ""))
        t_len = len(t.get("clean_text", ""))
        can_merge = (
            same_source
            and same_speaker
            and both_body
            and buf_len < MIN_CHARS
            and (buf_len + t_len) <= MAX_CHARS
        )
        if can_merge:
            buf["clean_text"] = buf["clean_text"].rstrip() + " " + t["clean_text"].lstrip()
            buf["_merged_turn_indices"].append(t["turn_index"])
            buf["_merged_from_chunk_ids"].append(
                f"{t['source_id']}_turn_{t['turn_index']:04d}"
            )
        else:
            merged.append(buf)
            buf = dict(t)
            buf["_merged_turn_indices"] = [t["turn_index"]]
            buf["_merged_from_chunk_ids"] = [
                f"{t['source_id']}_turn_{t['turn_index']:04d}"
            ]
    merged.append(buf)
    return merged


def _build_record_v2_1(chunk: dict, source_id: str, doc_hash: str) -> dict:
    raw_speaker = str(chunk.get("speaker", "") or "").strip()
    speaker = normalize_speaker_name(raw_speaker)
    speaker_role = chunk.get("speaker_role", "")
    clean_text = chunk.get("clean_text", "")
    section_type = chunk.get("section_type", "body")
    turn_index = chunk.get("turn_index", 0)
    merged_indices = chunk.get("_merged_turn_indices", [turn_index])
    merged_ids = chunk.get("_merged_from_chunk_ids", [])

    chunk_id = f"{source_id}_turn_{turn_index:04d}"
    chunk_hash = compute_chunk_hash(chunk_id, speaker, speaker_role, turn_index, clean_text, section_type)
    token_count = _count_tokens(clean_text)
    low_signal = is_low_signal(clean_text)
    search_ok = section_type == "body" and not low_signal

    meta = dict(chunk.get("metadata", {}))
    meta["token_count"] = token_count
    speaker_original = chunk.get("speaker_original") or None
    if not speaker_original and raw_speaker and raw_speaker != speaker and has_hanja(raw_speaker):
        speaker_original = raw_speaker
    if speaker_original:
        meta["speaker_original"] = speaker_original
    _enrich_speaker_metadata(meta, speaker, speaker_role)
    _enrich_question_type_metadata(meta, clean_text, speaker, speaker_role)

    enriched = {**chunk, "metadata": meta}

    record: dict = {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "page_no": chunk.get("page_no"),
        "turn_index": turn_index,
        "speaker": speaker,
        "speaker_role": speaker_role,
        "section_type": section_type,
        "raw_text": chunk.get("raw_text", clean_text),
        "clean_text": clean_text,
        "embed_text": _make_embed_text(enriched),
        "doc_hash": doc_hash,
        "chunk_hash": chunk_hash,
        "is_low_signal": low_signal,
        "search_eligible": search_ok,
        "merged_turn_indices": merged_indices,
        "merged_from_chunk_ids": merged_ids,
        "metadata": meta,
        "token_count": token_count,
    }
    return record


def process_source(turns_path: Path, final_out) -> dict:
    """단일 회의록을 처리하고 provenance 딕셔너리를 반환."""
    sid = turns_path.parent.name
    turns: list[dict] = []
    with turns_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))

    if not turns:
        return {}

    meta0 = turns[0].get("metadata", {})
    committee = meta0.get("committee", "")
    meeting_date = meta0.get("meeting_date", "")

    # section_type 분류
    for t in turns:
        t["section_type"] = classify_section_type(t.get("speaker", ""), t.get("clean_text", ""))

    # 30자 미만 no-speaker 제거 (커버 텍스트 제외)
    turns = [
        t for t in turns
        if len(t.get("clean_text", "")) >= LOW_SIGNAL_CHARS
        or t.get("speaker", "")
    ]

    # body turns만 병합 (non-body는 그대로 유지)
    body_turns = [t for t in turns if t.get("section_type") == "body"]
    non_body_turns = [t for t in turns if t.get("section_type") != "body"]

    merged_body = merge_turns_v2_1(body_turns)
    all_turns = sorted(non_body_turns + merged_body, key=lambda t: t.get("turn_index", 0))

    all_texts = [t.get("clean_text", "") for t in all_turns]
    doc_hash = compute_doc_hash(sid, meeting_date, committee, all_texts)

    records = [_build_record_v2_1(t, sid, doc_hash) for t in all_turns]
    records = _add_context_window(records)

    out_dir = CHUNKS_DIR / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            line = json.dumps(r, ensure_ascii=False) + "\n"
            f.write(line)
            final_out.write(line)

    # provenance 통계
    body_count = sum(1 for r in records if r["section_type"] == "body")
    speaker_missing = sum(1 for r in records if not r["speaker"])
    short_count = sum(1 for r in records if len(r["clean_text"]) < 300)
    low_signal_count = sum(1 for r in records if r["is_low_signal"])
    search_count = sum(1 for r in records if r["search_eligible"])
    lengths = [len(r["clean_text"]) for r in records]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    sorted_lens = sorted(lengths)
    n = len(sorted_lens)
    p50 = sorted_lens[n // 2] if n else 0

    section_dist: dict[str, int] = {}
    for r in records:
        s = r["section_type"]
        section_dist[s] = section_dist.get(s, 0) + 1

    return {
        "source_id": sid,
        "committee": committee,
        "meeting_date": meeting_date,
        "doc_hash": doc_hash,
        "turn_count": len(turns),
        "chunk_count": len(records),
        "body_chunk_count": body_count,
        "search_eligible_count": search_count,
        "speaker_missing_count": speaker_missing,
        "short_chunk_count": short_count,
        "low_signal_count": low_signal_count,
        "avg_chunk_length": round(avg_len, 1),
        "p50_chunk_length": p50,
        "section_dist": section_dist,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    final_path = OUT_DIR / "chunks_v2_1.jsonl"
    provenance_path = REPORTS_DIR / "provenance.jsonl"

    provenance: list[dict] = []

    with final_path.open("w", encoding="utf-8") as final_out:
        for turns_path in sorted(TURNS_DIR.glob("*/turns.jsonl")):
            prov = process_source(turns_path, final_out)
            if prov:
                provenance.append(prov)
                print(
                    f"  {prov['source_id']}: chunks={prov['chunk_count']}"
                    f" body={prov['body_chunk_count']}"
                    f" search={prov['search_eligible_count']}"
                )

    with provenance_path.open("w", encoding="utf-8") as f:
        for p in provenance:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    total = sum(p["chunk_count"] for p in provenance)
    total_search = sum(p["search_eligible_count"] for p in provenance)
    total_low = sum(p["low_signal_count"] for p in provenance)
    total_short = sum(p["short_chunk_count"] for p in provenance)
    total_spk_miss = sum(p["speaker_missing_count"] for p in provenance)

    print(f"\n[chunker_v2_1] 완료")
    print(f"  문서: {len(provenance)}건")
    print(f"  총 chunk: {total}개")
    print(f"  검색 대상 (search_eligible): {total_search}개")
    print(f"  low_signal: {total_low}개")
    print(f"  300자 미만: {total_short}개 ({total_short/max(total,1):.1%})")
    print(f"  speaker 누락: {total_spk_miss}개 ({total_spk_miss/max(total,1):.1%})")
    print(f"  → {final_path}")
    print(f"  → {provenance_path}")


if __name__ == "__main__":
    main()
