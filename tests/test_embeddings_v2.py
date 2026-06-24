import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.loader.embeddings_v2 import (
    _parse_db_row,
    _build_count_sql,
    _build_iter_sql,
)


def test_parse_db_row_all_fields():
    row = (42, "20240717_52128_turn_0084", "[회의일: 2024-07-17]\n발언 내용")
    result = _parse_db_row(row)
    assert result["id"] == 42
    assert result["chunk_id"] == "20240717_52128_turn_0084"
    assert result["embed_text"] == "[회의일: 2024-07-17]\n발언 내용"


def test_parse_db_row_key_is_embed_text_not_natural_text():
    row = (1, "cid", "embed content")
    result = _parse_db_row(row)
    assert "embed_text" in result
    assert "natural_text" not in result


def test_parse_db_row_empty_embed_text():
    row = (1, "cid", "")
    assert _parse_db_row(row)["embed_text"] == ""


def test_build_count_sql_skip_existing_has_left_join():
    sql = _build_count_sql(skip_existing=True)
    assert "LEFT JOIN embeddings_e5_v2" in sql
    assert "IS NULL" in sql


def test_build_count_sql_skip_existing_filters_body():
    sql = _build_count_sql(skip_existing=True)
    assert "section_type" in sql
    assert "body" in sql


def test_build_count_sql_all_counts_chunks_v2():
    sql = _build_count_sql(skip_existing=False)
    assert "chunks_v2" in sql
    assert "section_type" in sql
    assert "body" in sql


def test_build_iter_sql_with_limit():
    sql = _build_iter_sql(skip_existing=True, limit=500)
    assert "LIMIT 500" in sql


def test_build_iter_sql_no_limit():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "LIMIT" not in sql


def test_build_iter_sql_selects_embed_text():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "embed_text" in sql


def test_build_iter_sql_targets_embeddings_e5_v2():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "embeddings_e5_v2" in sql
    assert "embeddings_e5" not in sql.replace("embeddings_e5_v2", "")
