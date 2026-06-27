import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.chunker_v2 import _build_record, _make_chunk_id, _make_embed_text, _merge_turns

_META = {"meeting_date": "2024-07-17", "committee": "외교통일위원회"}


def _turn(text: str, speaker: str = "김철수", role: str = "위원", turn_index: int = 0) -> dict:
    return {
        "source_id": "20240717_52128_52128",
        "page_no": 5,
        "turn_index": turn_index,
        "speaker": speaker,
        "speaker_role": role,
        "section_type": "body",
        "clean_text": text,
        "metadata": _META,
    }


def test_make_chunk_id_zero_padded():
    assert _make_chunk_id(_turn("텍스트", turn_index=84)) == "20240717_52128_52128_turn_0084"


def test_make_chunk_id_small_index():
    assert _make_chunk_id(_turn("텍스트", turn_index=0)) == "20240717_52128_52128_turn_0000"


def test_make_embed_text_has_all_prefix_fields():
    result = _make_embed_text(_turn("교류 협력을 확대해야 합니다."))
    assert "[회의일: 2024-07-17]" in result
    assert "[위원회: 외교통일위원회]" in result
    assert "[발언자: 김철수 위원]" in result
    assert "교류 협력을 확대해야 합니다." in result


def test_make_embed_text_no_speaker():
    turn = _turn("발언 내용.", speaker="", role="")
    result = _make_embed_text(turn)
    assert "[발언자:" not in result
    assert "발언 내용." in result


def test_make_embed_text_body_on_new_line():
    result = _make_embed_text(_turn("본문입니다."))
    lines = result.splitlines()
    assert any("본문입니다." in l for l in lines)
    assert lines[0].startswith("[회의일:")


def test_build_record_adds_question_type_metadata_for_member_question():
    record = _build_record(
        _turn("통일부는 북한 인권 문제에 대해 어떤 대책을 갖고 있습니까?", speaker="김영배", role="위원"),
        "20240717_52128_52128",
    )
    meta = record["metadata"]
    assert meta["utterance_type"] == "question"
    assert "question_draft" in meta["question_type_hints"]
    assert "qa_pair_extract" in meta["question_type_hints"]
    assert "[발화유형: 질의]" in record["embed_text"]


def test_build_record_adds_agency_metadata_for_government_answer():
    record = _build_record(
        _turn("답변드리겠습니다. 통일부는 후속 조치를 검토하고 자료를 제출하겠습니다.", speaker="홍길동", role="통일부장관"),
        "20240717_52128_52128",
    )
    meta = record["metadata"]
    assert meta["position_type"] == "정부측"
    assert meta["utterance_type"] == "answer"
    assert meta["agency"] == "통일부"
    assert "agency_answer_tracking" in meta["question_type_hints"]
    assert "[기관: 통일부]" in record["embed_text"]


def test_merge_short_same_speaker():
    turns = [_turn("짧은 발언.", turn_index=0), _turn("이어지는 내용.", turn_index=1)]
    merged = _merge_turns(turns)
    assert len(merged) == 1
    assert "짧은 발언" in merged[0]["clean_text"]
    assert "이어지는 내용" in merged[0]["clean_text"]


def test_no_merge_different_speaker():
    turns = [
        _turn("발언1", speaker="김철수", turn_index=0),
        _turn("발언2", speaker="이영희", turn_index=1),
    ]
    assert len(_merge_turns(turns)) == 2


def test_no_merge_when_buf_long():
    long_text = "가나다라마바사" * 50  # 350자 > MIN_CHARS(300)
    turns = [_turn(long_text, turn_index=0), _turn("추가.", turn_index=1)]
    assert len(_merge_turns(turns)) == 2


def test_no_merge_when_result_exceeds_max():
    text_a = "가" * 400  # 400자
    text_b = "나" * 250  # 250자 → 합계 650 > MAX_CHARS(600)
    turns = [_turn(text_a, turn_index=0), _turn(text_b, turn_index=1)]
    assert len(_merge_turns(turns)) == 2


def test_merge_preserves_first_turn_index():
    turns = [_turn("짧음", turn_index=10), _turn("짧음2", turn_index=11)]
    merged = _merge_turns(turns)
    assert merged[0]["turn_index"] == 10


def test_build_record_has_utterance_type_confidence():
    record = _build_record(
        _turn("어떤 대책을 갖고 있습니까?", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert "utterance_type_confidence" in record["metadata"]
    conf = record["metadata"]["utterance_type_confidence"]
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0


def test_demand_statement_has_high_confidence():
    record = _build_record(
        _turn("철저한 대책 마련을 부탁드립니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    meta = record["metadata"]
    assert meta["utterance_type"] == "statement"
    assert meta["utterance_type_confidence"] >= 0.80


def test_build_record_has_issue_score():
    record = _build_record(
        _turn("예산 낭비와 비리가 쟁점입니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert "issue_score" in record["metadata"]
    score = record["metadata"]["issue_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_build_record_issue_score_high_for_issue_text():
    record = _build_record(
        _turn("예산 낭비와 비리 문제가 쟁점이 됩니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert record["metadata"]["issue_score"] >= 0.50
