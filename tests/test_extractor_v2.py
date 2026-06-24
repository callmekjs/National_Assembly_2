import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.extractor.extractor_v2 import _metadata_from_path, _source_id


def test_source_id_is_stem():
    path = Path("incoming_data/외교통일위원회/20240717_52128_52128.pdf")
    assert _source_id(path) == "20240717_52128_52128"


def test_metadata_date_from_filename():
    path = Path("incoming_data/외교통일위원회/20240717_52128_52128.pdf")
    meta = _metadata_from_path(path)
    assert meta["meeting_date"] == "2024-07-17"


def test_metadata_committee_from_path():
    path = Path("incoming_data/외교통일위원회/20240717_52128_52128.pdf")
    meta = _metadata_from_path(path)
    assert meta["committee"] == "외교통일위원회"


def test_metadata_no_date_in_filename():
    path = Path("incoming_data/외교통일위원회/unknown.pdf")
    meta = _metadata_from_path(path)
    assert meta["meeting_date"] == ""


def test_metadata_unknown_committee():
    path = Path("incoming_data/기타/20240717_52128.pdf")
    meta = _metadata_from_path(path)
    assert meta["committee"] == ""
