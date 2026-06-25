import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.chunker_v2_1 import (
    classify_section_type,
    compute_chunk_hash,
    compute_doc_hash,
    is_low_signal,
    merge_turns_v2_1,
)

SID = "20240717_52128_52128"
_META = {"meeting_date": "2024-07-17", "committee": "외교통일위원회"}


def _turn(text: str, speaker: str = "김철수", role: str = "위원", turn_index: int = 0, section_type: str = "body") -> dict:
    return {
        "source_id": SID,
        "page_no": 5,
        "turn_index": turn_index,
        "speaker": speaker,
        "speaker_role": role,
        "section_type": section_type,
        "raw_text": text,
        "clean_text": text,
        "metadata": dict(_META),
    }


# --- section_type 분류 ---

def test_classify_no_speaker_with_hosu_becomes_cover():
    stype = classify_section_type("", "2 제416회-외교통일제1차(2024년7월17일)")
    assert stype == "cover"


def test_classify_no_speaker_default_cover():
    stype = classify_section_type("", "일반적인 텍스트입니다.")
    assert stype == "cover"


def test_classify_agenda():
    stype = classify_section_type("김석기", "다음 의사일정을 처리하도록 하겠습니다.")
    assert stype == "agenda"


def test_classify_procedural_gaewi():
    stype = classify_section_type("김석기", "지금부터 개의를 선언합니다.")
    assert stype == "procedural"


def test_classify_procedural_sanhwe():
    stype = classify_section_type("김석기", "이상으로 산회를 선언합니다.")
    assert stype == "procedural"


def test_classify_body():
    stype = classify_section_type("김영배", "통일부는 북한 인권 문제에 대해 어떤 입장인지 말씀해 주십시오.")
    assert stype == "body"


def test_classify_appendix_no_speaker():
    stype = classify_section_type("", "붙임 1. 관련 자료")
    assert stype == "appendix"


# --- is_low_signal ---

def test_low_signal_yes():
    assert is_low_signal("예") is True


def test_low_signal_gamsa():
    assert is_low_signal("감사합니다") is True


def test_low_signal_long_text():
    assert is_low_signal("이 내용은 충분히 길어서 신호 가치가 있는 발언입니다.") is False


def test_low_signal_threshold():
    assert is_low_signal("가" * 30) is False


# --- merge_turns_v2_1 ---

def test_merge_same_speaker_short():
    turns = [_turn("짧은 발언.", turn_index=0), _turn("이어지는 내용.", turn_index=1)]
    merged = merge_turns_v2_1(turns)
    assert len(merged) == 1
    assert "짧은 발언" in merged[0]["clean_text"]
    assert "이어지는 내용" in merged[0]["clean_text"]


def test_merge_tracks_turn_indices():
    turns = [_turn("짧음", turn_index=5), _turn("이어짐", turn_index=6)]
    merged = merge_turns_v2_1(turns)
    assert merged[0]["_merged_turn_indices"] == [5, 6]


def test_merge_tracks_chunk_ids():
    turns = [_turn("짧음", turn_index=3), _turn("이어짐", turn_index=4)]
    merged = merge_turns_v2_1(turns)
    ids = merged[0]["_merged_from_chunk_ids"]
    assert f"{SID}_turn_0003" in ids
    assert f"{SID}_turn_0004" in ids


def test_no_merge_different_speaker():
    turns = [
        _turn("발언1", speaker="김철수", turn_index=0),
        _turn("발언2", speaker="이영희", turn_index=1),
    ]
    assert len(merge_turns_v2_1(turns)) == 2


def test_no_merge_empty_speaker():
    turns = [
        _turn("발언1", speaker="", turn_index=0),
        _turn("발언2", speaker="", turn_index=1),
    ]
    result = merge_turns_v2_1(turns)
    assert len(result) == 2


def test_no_merge_non_body_sections():
    t0 = _turn("개의를 선언합니다.", turn_index=0, section_type="procedural")
    t1 = _turn("개의를 알립니다.", turn_index=1, section_type="procedural")
    result = merge_turns_v2_1([t0, t1])
    assert len(result) == 2


def test_no_merge_when_buf_already_long():
    long_text = "가나다라마바사" * 50
    turns = [_turn(long_text, turn_index=0), _turn("추가.", turn_index=1)]
    assert len(merge_turns_v2_1(turns)) == 2


def test_no_merge_when_result_exceeds_max():
    text_a = "가" * 400
    text_b = "나" * 250
    turns = [_turn(text_a, turn_index=0), _turn(text_b, turn_index=1)]
    assert len(merge_turns_v2_1(turns)) == 2


def test_single_turn_indices_list():
    turns = [_turn("단독 발언.", turn_index=7)]
    merged = merge_turns_v2_1(turns)
    assert merged[0]["_merged_turn_indices"] == [7]


# --- 해시 ---

def test_doc_hash_deterministic():
    h1 = compute_doc_hash(SID, "2024-07-17", "외교통일위원회", ["텍스트A", "텍스트B"])
    h2 = compute_doc_hash(SID, "2024-07-17", "외교통일위원회", ["텍스트A", "텍스트B"])
    assert h1 == h2


def test_doc_hash_changes_with_text():
    h1 = compute_doc_hash(SID, "2024-07-17", "외교통일위원회", ["텍스트A"])
    h2 = compute_doc_hash(SID, "2024-07-17", "외교통일위원회", ["텍스트B"])
    assert h1 != h2


def test_chunk_hash_deterministic():
    h1 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "텍스트", "body")
    h2 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "텍스트", "body")
    assert h1 == h2


def test_chunk_hash_changes_with_clean_text():
    h1 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "원본 텍스트", "body")
    h2 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "수정된 텍스트", "body")
    assert h1 != h2


def test_chunk_hash_changes_with_section_type():
    h1 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "텍스트", "body")
    h2 = compute_chunk_hash("chunk_001", "김철수", "위원", 5, "텍스트", "procedural")
    assert h1 != h2
