import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.loader.jsonl_to_postgres_v2 import _row_to_tuple, INSERT_SQL


def _sample_row() -> dict:
    return {
        "chunk_id": "20240717_52128_turn_0084",
        "source_id": "20240717_52128",
        "page_no": 12,
        "turn_index": 84,
        "section_type": "body",
        "speaker": "권칠승",
        "speaker_role": "위원",
        "raw_text": "원문 텍스트입니다.",
        "clean_text": "정제된 텍스트입니다.",
        "embed_text": "[회의일: 2024-07-17] [위원회: 외교통일위원회] [발언자: 권칠승 위원]\n정제된 텍스트입니다.",
        "metadata": {"committee": "외교통일위원회", "meeting_date": "2024-07-17"},
    }


def test_row_to_tuple_length():
    tup = _row_to_tuple(_sample_row())
    assert len(tup) == 11


def test_row_to_tuple_chunk_id():
    assert _row_to_tuple(_sample_row())[0] == "20240717_52128_turn_0084"


def test_row_to_tuple_source_id():
    assert _row_to_tuple(_sample_row())[1] == "20240717_52128"


def test_row_to_tuple_page_no_int():
    assert _row_to_tuple(_sample_row())[2] == 12


def test_row_to_tuple_turn_index_int():
    assert _row_to_tuple(_sample_row())[3] == 84


def test_row_to_tuple_section_type():
    assert _row_to_tuple(_sample_row())[4] == "body"


def test_row_to_tuple_embed_text_position():
    tup = _row_to_tuple(_sample_row())
    assert "[회의일: 2024-07-17]" in tup[9]


def test_row_to_tuple_metadata_is_dict():
    tup = _row_to_tuple(_sample_row())
    meta = tup[10]
    assert isinstance(meta.adapted, dict)
    assert meta.adapted["committee"] == "외교통일위원회"


def test_row_to_tuple_defaults_for_missing_fields():
    row = {"chunk_id": "cid", "raw_text": "r", "clean_text": "c", "embed_text": "e"}
    tup = _row_to_tuple(row)
    assert tup[1] == ""   # source_id
    assert tup[2] is None  # page_no
    assert tup[3] is None  # turn_index
    assert tup[4] == ""   # section_type


def test_insert_sql_targets_chunks_v2():
    assert "chunks_v2" in INSERT_SQL
    assert "chunks" not in INSERT_SQL.replace("chunks_v2", "")


def test_insert_sql_has_on_conflict():
    assert "ON CONFLICT (chunk_id) DO UPDATE" in INSERT_SQL


def test_load_qa_pairs_calls_load_with_qa_path(monkeypatch, tmp_path):
    """load_chunks_v2가 qa_pairs 파일도 처리하는지 확인 (실제 DB 없이 경로 검증)."""
    import json
    from service.etl.loader import jsonl_to_postgres_v2

    qa_file = tmp_path / "qa_pairs_v2.jsonl"
    qa_file.write_text(
        json.dumps({
            "chunk_id": "S1_qa_0000", "source_id": "S1",
            "page_no": 1, "turn_index": 0, "section_type": "body",
            "speaker": "이재정 → 조태열", "speaker_role": "위원 → 장관",
            "raw_text": "[질의]\n질의\n\n[답변]\n답변",
            "clean_text": "[질의]\n질의\n\n[답변]\n답변",
            "embed_text": "[회의일: 2024-10-15] 질의 답변",
            "metadata": {"chunk_type": "qa_pair", "utterance_type": "qa_pair",
                         "committee": "외교통일위원회", "meeting_date": "2024-10-15"},
        }, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    inserted = []

    def fake_load(jsonl_path=None, batch_size=1000):
        if jsonl_path:
            inserted.append(str(jsonl_path))
        return True

    monkeypatch.setattr(jsonl_to_postgres_v2, "load_chunks_v2", fake_load)
    jsonl_to_postgres_v2.load_qa_pairs(qa_file)
    assert str(qa_file) in inserted
