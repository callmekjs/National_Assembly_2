from __future__ import annotations
import pytest
from service.etl.transform.qa_pairer_v2 import pair_qa_chunks

def _turn(source_id, turn_index, utterance_type, speaker, speaker_role,
          position_type, text, page_no=1, meeting_date="2024-10-15", committee="외교통일위원회"):
    return {
        "chunk_id": f"{source_id}_turn_{turn_index:04d}",
        "source_id": source_id,
        "turn_index": turn_index,
        "page_no": page_no,
        "section_type": "body",
        "speaker": speaker,
        "speaker_role": speaker_role,
        "clean_text": text,
        "raw_text": text,
        "embed_text": text,
        "metadata": {
            "utterance_type": utterance_type,
            "position_type": position_type,
            "committee": committee,
            "meeting_date": meeting_date,
            "party": "더불어민주당" if position_type == "의원" else "정부",
            "question_type_hints": ["qa_pair_extract"] if utterance_type in ("question", "answer") else [],
        },
    }


# ── 케이스 1: 단순 Q→A 1쌍 ──────────────────────────────────────
def test_simple_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "대북제재 입장이 어떻습니까?"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "제재 기조 유지하겠습니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["metadata"]["chunk_type"] == "qa_pair"
    assert p["metadata"]["question_speaker"] == "이재정"
    assert p["metadata"]["answer_speaker"] == "조태열"
    assert "[질의]" in p["clean_text"]
    assert "[답변]" in p["clean_text"]
    assert p["chunk_id"].startswith("SRC1_qa_")


# ── 케이스 2: 연속 질의 (같은 질의자) → 1쌍 ─────────────────────
def test_multi_question_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "첫째 질의입니다."),
        _turn("SRC1", 1, "question", "이재정", "위원", "의원", "둘째 질의입니다."),
        _turn("SRC1", 2, "answer",   "조태열", "장관", "정부측", "두 질의에 답합니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    assert "첫째 질의입니다." in pairs[0]["clean_text"]
    assert "둘째 질의입니다." in pairs[0]["clean_text"]


# ── 케이스 3: 연속 답변 (같은 답변자) → 1쌍 ─────────────────────
def test_multi_answer_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "질의입니다."),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "첫째 답변입니다."),
        _turn("SRC1", 2, "answer",   "조태열", "장관", "정부측", "둘째 답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    assert "첫째 답변입니다." in pairs[0]["clean_text"]
    assert "둘째 답변입니다." in pairs[0]["clean_text"]


# ── 케이스 4: 두 개의 독립적인 Q-A 쌍 ───────────────────────────
def test_two_independent_pairs():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "첫 질의"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "첫 답변"),
        _turn("SRC1", 2, "question", "김석기", "위원", "의원", "둘째 질의"),
        _turn("SRC1", 3, "answer",   "조태열", "장관", "정부측", "둘째 답변"),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 2
    assert pairs[0]["metadata"]["question_speaker"] == "이재정"
    assert pairs[1]["metadata"]["question_speaker"] == "김석기"


# ── 케이스 5: 답변 없는 질의 (procedural이 끊음) → 0쌍 ──────────
def test_unanswered_question_emits_nothing():
    turns = [
        _turn("SRC1", 0, "question",   "이재정", "위원", "의원", "질의합니다."),
        _turn("SRC1", 1, "procedural", "김석기", "위원장", "위원장", "잠시 정회하겠습니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 6: 고아 답변 (질의 없는 답변) → 0쌍 ──────────────────
def test_orphan_answer_skipped():
    turns = [
        _turn("SRC1", 0, "answer", "조태열", "장관", "정부측", "보충 답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 7: turn_index 갭 > 8 → 질의가 폐기됨 ─────────────────
def test_large_gap_discards_question():
    turns = [
        _turn("SRC1", 0,  "question", "이재정", "위원", "의원", "질의합니다."),
        _turn("SRC1", 10, "answer",   "조태열", "장관", "정부측", "답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 8: 빈 입력 ───────────────────────────────────────────
def test_empty_input():
    assert pair_qa_chunks([]) == []


# ── 케이스 9: chunk_id 형식 검증 ───────────────────────────────
def test_chunk_id_format():
    turns = [
        _turn("DOC_001", 0, "question", "이재정", "위원", "의원", "질의"),
        _turn("DOC_001", 1, "answer",   "조태열", "장관", "정부측", "답변"),
        _turn("DOC_001", 2, "question", "김석기", "위원", "의원", "질의2"),
        _turn("DOC_001", 3, "answer",   "조태열", "장관", "정부측", "답변2"),
    ]
    pairs = pair_qa_chunks(turns)
    assert pairs[0]["chunk_id"] == "DOC_001_qa_0000"
    assert pairs[1]["chunk_id"] == "DOC_001_qa_0001"


# ── 케이스 10: embed_text에 필수 메타 포함 ─────────────────────
def test_embed_text_contains_meta():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "질의"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "답변"),
    ]
    pairs = pair_qa_chunks(turns)
    embed = pairs[0]["embed_text"]
    assert "외교통일위원회" in embed
    assert "2024-10-15" in embed
    assert "이재정" in embed
    assert "조태열" in embed
