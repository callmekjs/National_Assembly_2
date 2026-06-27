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
