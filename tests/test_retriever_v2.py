import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.retrieval.retriever import _rrf_merge


def _hit(chunk_id: str, content: str = "내용") -> dict:
    return {"chunk_id": chunk_id, "content": content, "similarity": 0.9, "source_id": "src"}


def test_empty_both_returns_empty():
    assert _rrf_merge([], []) == []


def test_vector_only():
    result = _rrf_merge([_hit("A"), _hit("B")], [])
    assert [r["chunk_id"] for r in result] == ["A", "B"]


def test_fts_only():
    result = _rrf_merge([], [_hit("C"), _hit("D")])
    assert [r["chunk_id"] for r in result] == ["C", "D"]


def test_overlap_deduplicates():
    vector = [_hit("A"), _hit("B")]
    fts = [_hit("B"), _hit("C")]
    result = _rrf_merge(vector, fts)
    ids = [r["chunk_id"] for r in result]
    assert len(ids) == len(set(ids))


def test_overlap_boosts_score():
    # B가 두 리스트 모두 rank=1 → A(벡터 rank=2)보다 높아야 함
    vector = [_hit("A"), _hit("B")]
    fts = [_hit("B"), _hit("C")]
    result = _rrf_merge(vector, fts)
    ids = [r["chunk_id"] for r in result]
    assert ids[0] == "B"


def test_top_n_limits_output():
    vector = [_hit(f"V{i}") for i in range(10)]
    fts = [_hit(f"F{i}") for i in range(10)]
    result = _rrf_merge(vector, fts, top_n=5)
    assert len(result) == 5


from service.rag.retrieval.retriever import (
    _parse_turn_index,
    _merge_adjacent_hits,
    _apply_chronological_sort,
    _ADJACENT_GAP,
    _MERGE_MAX_CHARS,
)


def _hit_merge(source_id: str, turn: int, content: str = "내용", score: float = 0.5) -> dict:
    return {
        "chunk_id": f"{source_id}_turn_{turn:04d}",
        "source_id": source_id,
        "content": content,
        "hybrid_score": score,
    }


def test_parse_turn_index_standard():
    assert _parse_turn_index("20240717_52128_52128_turn_0003") == 3


def test_parse_turn_index_none_for_qa():
    assert _parse_turn_index("20240717_52128_52128_qa_0001") is None


def test_parse_turn_index_none_for_empty():
    assert _parse_turn_index("") is None


def test_merge_adjacent_two_hits():
    hits = [_hit_merge("src", 1, "A내용", 0.9), _hit_merge("src", 2, "B내용", 0.7)]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 1
    assert "A내용" in result[0]["content"]
    assert "B내용" in result[0]["content"]
    assert result[0]["hybrid_score"] == 0.9
    assert result[0]["_merged_chunk_ids"] == ["src_turn_0001", "src_turn_0002"]


def test_merge_gap_beyond_threshold_not_merged():
    hits = [_hit_merge("src", 1, "A", 0.9), _hit_merge("src", 4, "B", 0.7)]  # gap=3 > _ADJACENT_GAP=2
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_different_source_not_merged():
    hits = [_hit_merge("srcA", 1, "A"), _hit_merge("srcB", 2, "B")]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_chronological_order():
    # hit B (turn 3) ranked higher but has earlier turn than hit A (turn 5)
    hits = [_hit_merge("src", 5, "나중발언", 0.9), _hit_merge("src", 3, "이전발언", 0.7)]
    result = _merge_adjacent_hits(hits, gap=2)
    assert len(result) == 1
    assert result[0]["content"].index("이전발언") < result[0]["content"].index("나중발언")


def test_merge_max_chars_exceeded_not_merged():
    long_a = "가" * 700
    long_b = "나" * 700
    hits = [_hit_merge("src", 1, long_a), _hit_merge("src", 2, long_b)]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_single_hit_unchanged():
    hits = [_hit_merge("src", 1, "혼자")]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 1
    assert result[0]["content"] == "혼자"


def test_rrf_score_field_present():
    result = _rrf_merge([_hit("A")], [])
    assert "rrf_score" in result[0]


def test_rrf_score_correct_formula():
    # rank=1, k=60 → score = 1/61 ≈ 0.016393 (rounded to 6 decimal places)
    result = _rrf_merge([_hit("A")], [])
    assert abs(result[0]["rrf_score"] - 1 / 61) < 1e-6


from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST, _apply_importance_boost, _IMPORTANCE_BOOST


def test_apply_issue_boost_reorders_for_issue_extract():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"issue_score": 0.0}},
        {"hybrid_score": 0.70, "metadata": {"issue_score": 1.0}},
    ]
    result = _apply_issue_boost(hits, question_type="issue_extract")
    # second hit: 0.70 + 0.15 * 1.0 = 0.85 > 0.80 → moves to first
    assert result[0]["metadata"]["issue_score"] == 1.0
    assert result[0]["hybrid_score"] == pytest.approx(0.85)


def test_apply_issue_boost_noop_for_other_types():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"issue_score": 0.0}},
        {"hybrid_score": 0.70, "metadata": {"issue_score": 1.0}},
    ]
    result = _apply_issue_boost(hits, question_type="topic_search")
    assert result[0]["hybrid_score"] == 0.80


def test_apply_importance_boost_reorders_for_topic_search():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="topic_search")
    # second hit: 0.72 + 0.10 * 1.0 = 0.82 > 0.80 → moves to first
    assert result[0]["metadata"]["importance_score"] == 1.0
    assert result[0]["hybrid_score"] == pytest.approx(0.82)


def test_apply_importance_boost_noop_for_issue_extract():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="issue_extract")
    assert result[0]["hybrid_score"] == 0.80


from service.rag.retrieval.retriever import _resolve_agency_filter


def test_resolve_agency_filter_extracts_agency_and_forces_answer():
    agency, utype = _resolve_agency_filter(
        "외교부가 재외국민 보호에 대해 뭐라 했나?", "agency_answer_tracking", None, None
    )
    assert agency == "외교부"
    assert utype == "answer"


def test_resolve_agency_filter_noop_for_topic_search():
    agency, utype = _resolve_agency_filter("외교부 정책", "topic_search", None, None)
    assert agency == ""
    assert utype == ""


def test_resolve_agency_filter_preserves_explicit_agency():
    agency, utype = _resolve_agency_filter("질의", "agency_answer_tracking", "통일부", None)
    assert agency == "통일부"
    assert utype == "answer"


def test_resolve_agency_filter_no_match_returns_empty_agency():
    agency, utype = _resolve_agency_filter("일반 정책 질의", "agency_answer_tracking", None, None)
    assert agency == ""
    assert utype == "answer"


import inspect
from service.rag.retrieval.retriever import Retriever


def test_search_signature_has_use_smart_merge():
    sig = inspect.signature(Retriever.search)
    assert "use_smart_merge" in sig.parameters
    assert sig.parameters["use_smart_merge"].default is True


def _dated_hit(date: str, turn: int, score: float = 0.5) -> dict:
    return {
        "chunk_id": f"src_{date.replace('-', '')}_turn_{turn:04d}",
        "source_id": f"src_{date.replace('-', '')}",
        "content": f"발언 {date} turn={turn}",
        "hybrid_score": score,
        "metadata": {"meeting_date": date},
    }


def test_chronological_sort_comparison_orders_by_date():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="comparison")
    assert result[0]["metadata"]["meeting_date"] == "2024-03-01"
    assert result[1]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_meeting_summary_orders_by_date_then_turn():
    hits = [
        _dated_hit("2024-03-01", 5, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="meeting_summary")
    assert result[0]["chunk_id"].endswith("_turn_0002")
    assert result[1]["chunk_id"].endswith("_turn_0005")


def test_chronological_sort_noop_for_topic_search():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="topic_search")
    # 순서 그대로 유지 (2024-06 first)
    assert result[0]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_noop_for_none_question_type():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type=None)
    assert result[0]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_handles_missing_date():
    hits = [
        {"chunk_id": "src_turn_0001", "source_id": "src", "content": "A", "hybrid_score": 0.9, "metadata": {}},
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    # date 없는 항목은 "" → 앞으로 정렬됨 (빈 문자열이 날짜보다 앞)
    result = _apply_chronological_sort(hits, question_type="comparison")
    assert len(result) == 2  # 개수 변화 없음


def test_chronological_sort_empty_hits():
    result = _apply_chronological_sort([], question_type="comparison")
    assert result == []


def test_search_v2_signature_has_use_smart_merge():
    sig = inspect.signature(Retriever.search_v2)
    assert "use_smart_merge" in sig.parameters
    assert sig.parameters["use_smart_merge"].default is True
