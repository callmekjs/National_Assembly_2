import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.query.question_types import classify_question, route_defaults


def test_classify_source_check():
    assert classify_question("이 발언 원문 출처와 페이지 알려줘") == "source_check"


def test_classify_question_draft():
    assert classify_question("국감 질의서 초안을 작성해줘") == "question_draft"


def test_classify_qa_pair_extract():
    assert classify_question("위원 질의-답변 쌍으로 정리해줘") == "qa_pair_extract"


def test_classify_agency_answer_tracking():
    assert classify_question("통일부 답변과 후속 조치 추적해줘") == "agency_answer_tracking"


def test_classify_comparison():
    assert classify_question("과거와 현재 발언 차이를 비교해줘") == "comparison"


def test_classify_meeting_summary():
    assert classify_question("이 회의록 요약해줘") == "meeting_summary"


def test_classify_issue_extract():
    assert classify_question("북핵 관련 핵심 쟁점을 정리해줘") == "issue_extract"


def test_classify_speaker_search():
    assert classify_question("김영배 의원 발언 찾아줘") == "speaker_search"


def test_route_defaults_comparison_balances_speakers():
    defaults = route_defaults("comparison")
    assert defaults["balance_speakers"] is True
    assert defaults["answer_mode"] == "comparison"


def test_route_defaults_extract_type_sets_filter():
    defaults = route_defaults("qa_pair_extract")
    assert defaults["question_type_filter"] == "qa_pair_extract"
