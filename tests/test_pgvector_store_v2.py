import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.vectorstore.pgvector_store import _build_v2_filter_where


def test_empty_filters_body_only():
    where, params = _build_v2_filter_where(None)
    assert "c.section_type = 'body'" in where
    # chunk_type default filter is always appended
    assert "utterance" in params


def test_empty_dict_body_only():
    where, params = _build_v2_filter_where({})
    assert "c.section_type = 'body'" in where
    # chunk_type default filter is always appended
    assert "utterance" in params


def test_committee_filter():
    where, params = _build_v2_filter_where({"committee": "외교통일위원회"})
    assert "committee" in where
    assert "외교통일위원회" in params


def test_date_from_filter():
    where, params = _build_v2_filter_where({"date_from": "2024-01-01"})
    assert ">=" in where
    assert "2024-01-01" in params


def test_date_to_filter():
    where, params = _build_v2_filter_where({"date_to": "2024-12-31"})
    assert "<=" in where
    assert "2024-12-31" in params


def test_speaker_filter_uses_column_not_metadata():
    where, params = _build_v2_filter_where({"speaker": "김철수"})
    assert "c.speaker" in where
    # speaker uses c.speaker column, not a metadata->>'speaker' lookup
    assert "metadata->>'speaker'" not in where
    assert "%김철수%" in params


def test_multiple_filters_combined():
    where, params = _build_v2_filter_where({
        "committee": "외교통일위원회",
        "date_from": "2024-01-01",
        "speaker": "김철수",
    })
    assert where.count(" AND ") >= 3
    # 3 explicit filters + 1 chunk_type default = 4 params
    assert len(params) == 4


def test_question_type_filter_uses_jsonb_hint():
    where, params = _build_v2_filter_where({"question_type": "qa_pair_extract"})
    assert "question_type_hints" in where
    assert "?" in where
    assert "qa_pair_extract" in params


def test_utterance_and_agency_filters():
    where, params = _build_v2_filter_where({
        "utterance_type": "answer",
        "agency": "통일부",
    })
    assert "utterance_type" in where
    assert "agency" in where
    assert "answer" in params
    assert "통일부" in params


def test_build_v2_filter_default_excludes_qa_pairs():
    """chunk_type 필터 없을 때 기본으로 utterance만 선택."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where({})
    assert "chunk_type" in sql
    assert "utterance" in params


def test_build_v2_filter_qa_pair_mode():
    """chunk_type='qa_pair' 지정 시 qa_pair 레코드만 선택."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where({"chunk_type": "qa_pair"})
    assert "chunk_type" in sql
    assert "qa_pair" in params


def test_build_v2_filter_none_defaults_to_utterance():
    """filters=None 일 때도 utterance 기본 적용."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where(None)
    assert "chunk_type" in sql
    assert "utterance" in params
