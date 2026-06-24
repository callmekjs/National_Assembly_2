import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.normalizer_v2 import clean_text, classify_section


def test_classify_body_with_speaker_marker():
    assert classify_section("◯위원장 김석기 회의를 시작하겠습니다.") == "body"


def test_classify_body_overrides_appendix_phrase():
    raw = "◯위원장 김석기 열심히 설명 드렸습니다. 이상입니다."
    assert classify_section(raw) == "body"


def test_classify_agenda():
    assert classify_section("의 사 일 정\n1. 외교통일에 관한 질의") == "agenda"


def test_classify_cover():
    assert classify_section("국 회 사 무 처\n외교통일위원회 회의록") == "cover"


def test_classify_appendix():
    assert classify_section("보 고 사 항\n1. 외교부 현안 보고") == "appendix"


def test_classify_body_default():
    assert classify_section("일반 텍스트 내용입니다.") == "body"


def test_clean_removes_standalone_page_number():
    raw = "본문 내용입니다.\n12\n다음 내용입니다."
    result = clean_text(raw)
    assert "12" not in result.splitlines()


def test_clean_fixes_korean_word_split():
    raw = "남북 간 교\n류 협력 사업"
    result = clean_text(raw)
    assert "교\n류" not in result
    assert "교류" in result


def test_clean_removes_dot_leader():
    raw = "제1항 ........ 12\n실제 발언 내용"
    result = clean_text(raw)
    assert "........" not in result


def test_clean_removes_committee_header():
    raw = "외교통일위원회회의록\n◯위원장 김석기 시작합니다."
    result = clean_text(raw)
    assert "외교통일위원회회의록" not in result


def test_clean_removes_national_assembly_footer():
    raw = "본문 내용\n국 회 사 무 처\n다음 내용"
    result = clean_text(raw)
    lines = result.splitlines()
    assert not any("국 회 사 무 처" in l for l in lines)


def test_clean_removes_session_header():
    raw = "제416회-외교통일제1차(임시회)\n실제 발언 내용입니다."
    result = clean_text(raw)
    assert "제416회" not in result
