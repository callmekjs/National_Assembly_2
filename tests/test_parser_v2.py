import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.parser_v2 import extract_turns


def test_extracts_single_turn():
    turns = extract_turns("src_001", 1, "◯위원장 김석기 회의를 시작하겠습니다.")
    assert len(turns) == 1
    assert turns[0]["speaker"] == "김석기"
    assert turns[0]["speaker_role"] == "위원장"
    assert "회의를 시작하겠습니다" in turns[0]["clean_text"]


def test_role_before_name():
    turns = extract_turns("src_001", 1, "◯위원장 박민준 발언 내용입니다.")
    assert turns[0]["speaker"] == "박민준"
    assert turns[0]["speaker_role"] == "위원장"


def test_role_after_name():
    turns = extract_turns("src_001", 2, "◯조태열 장관 외교 정책에 대해 말씀드리겠습니다.")
    assert turns[0]["speaker"] == "조태열"
    assert turns[0]["speaker_role"] == "장관"


def test_extracts_multiple_turns():
    text = "◯위원장 김석기 첫 번째 발언입니다.\n◯홍길동 위원 두 번째 발언입니다."
    turns = extract_turns("src_001", 1, text)
    assert len(turns) == 2
    assert turns[0]["speaker"] == "김석기"
    assert turns[1]["speaker"] == "홍길동"
    assert turns[1]["speaker_role"] == "위원"


def test_turn_index_sequential():
    text = "◯김철수 위원 발언1\n◯이영희 장관 발언2\n◯박민준 위원장 발언3"
    turns = extract_turns("src_001", 1, text)
    assert [t["turn_index"] for t in turns] == [0, 1, 2]


def test_page_no_preserved():
    turns = extract_turns("src_001", 7, "◯김철수 위원 발언 내용입니다.")
    assert turns[0]["page_no"] == 7


def test_source_id_preserved():
    turns = extract_turns("20240717_52128", 1, "◯김철수 위원 발언 내용입니다.")
    assert turns[0]["source_id"] == "20240717_52128"


def test_skips_empty_body():
    text = "◯위원장 김석기\n◯홍길동 위원 실제 발언 내용입니다."
    turns = extract_turns("src_001", 1, text)
    for t in turns:
        assert t["clean_text"].strip()


def test_section_type_is_body():
    turns = extract_turns("src_001", 1, "◯김철수 위원 발언 내용입니다.")
    assert turns[0]["section_type"] == "body"
