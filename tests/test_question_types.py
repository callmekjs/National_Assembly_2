import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.query.question_types import classify_question, route_defaults, infer_utterance_type


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


def test_demand_ending_without_info_seeking_is_statement():
    result = infer_utterance_type(
        "북한 인권 문제에 대해 정부가 보다 적극적인 대응에 나서주시기 부탁드립니다.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "statement"


def test_request_ending_without_info_seeking_is_statement():
    result = infer_utterance_type(
        "이 사안에 대해 철저한 조사와 대책 마련을 요청드립니다.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "statement"


def test_demand_plus_info_seeking_is_question():
    result = infer_utterance_type(
        "이 법안 처리를 촉구합니다. 장관은 어떻게 생각하십니까?",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_pure_info_seeking_remains_question():
    result = infer_utterance_type(
        "통일부는 북한 인권 문제에 대해 어떤 대책을 갖고 있습니까?",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_explanation_request_remains_question():
    result = infer_utterance_type(
        "왜 그 결정을 하셨는지 설명해 주십시오.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_government_answer_unchanged():
    result = infer_utterance_type(
        "답변드리겠습니다. 해당 사안은 검토 후 조치하겠습니다.",
        speaker_role="통일부장관",
        position_type="정부측",
    )
    assert result == "answer"
