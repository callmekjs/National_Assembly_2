"""
service.etl.transform.normalizer 단위 테스트

실행:
  pytest tests/test_normalizer.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.normalizer import _normalize_text, _normalize_metadata


# ── _normalize_text ──────────────────────────────────────────────────

class TestNormalizeText:
    def test_removes_null_bytes(self):
        result = _normalize_text("텍스트\x00내용")
        assert "\x00" not in result
        assert "텍스트" in result

    def test_removes_bom(self):
        result = _normalize_text("﻿텍스트")
        assert "﻿" not in result

    def test_removes_zero_width_space(self):
        result = _normalize_text("텍스트​내용")
        assert "​" not in result

    def test_collapses_multiple_spaces(self):
        result = _normalize_text("텍스트    내용")
        assert "    " not in result
        assert "텍스트" in result and "내용" in result

    def test_collapses_blank_lines(self):
        result = _normalize_text("첫 줄\n\n\n\n두 번째 줄")
        assert "\n\n\n" not in result

    def test_tabs_replaced(self):
        result = _normalize_text("텍스트\t내용")
        assert "\t" not in result

    def test_empty_string(self):
        result = _normalize_text("")
        assert result == ""

    def test_normal_text_preserved(self):
        text = "외교부장관 조태열 위원이 발언하였습니다."
        result = _normalize_text(text)
        assert "외교부장관" in result
        assert "조태열" in result


# ── _normalize_metadata ──────────────────────────────────────────────

class TestNormalizeMetadata:
    def test_speaker_from_text(self):
        md = _normalize_metadata({}, "◯외교부장관 발언 시작입니다.")
        assert md.get("speaker") == "외교부장관"

    def test_existing_speaker_not_overwritten(self):
        md = _normalize_metadata({"speaker": "조태열"}, "◯홍길동 발언입니다.")
        assert md["speaker"] == "조태열"

    def test_committee_from_text(self):
        md = _normalize_metadata({}, "외교통일위원회회의록 내용입니다.")
        assert md.get("committee") == "외교통일위원회"

    def test_existing_committee_not_overwritten(self):
        md = _normalize_metadata({"committee": "국방위원회"}, "외교통일위원회회의록")
        assert md["committee"] == "국방위원회"

    def test_meeting_date_extracted(self):
        md = _normalize_metadata({}, "2026년 3월 15일 회의록입니다.")
        assert md.get("meeting_date") == "2026-03-15"

    def test_meeting_date_single_digit_month(self):
        md = _normalize_metadata({}, "2025년 6월 3일 회의록입니다.")
        assert md.get("meeting_date") == "2025-06-03"

    def test_existing_date_not_overwritten(self):
        md = _normalize_metadata({"meeting_date": "2024-01-01"}, "2026년 3월 15일")
        assert md["meeting_date"] == "2024-01-01"

    def test_empty_metadata_and_text(self):
        md = _normalize_metadata({}, "")
        assert isinstance(md, dict)
