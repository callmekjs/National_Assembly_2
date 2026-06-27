import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.query.question_types import classify_question, route_defaults, infer_utterance_type, infer_utterance_type_with_confidence, infer_issue_score, infer_importance_score, extract_agency_from_query


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


def test_confidence_clear_question_high():
    utype, conf = infer_utterance_type_with_confidence(
        "어떤 대책을 갖고 있습니까?", speaker_role="위원", position_type="의원"
    )
    assert utype == "question"
    assert conf >= 0.85


def test_confidence_demand_statement_high():
    utype, conf = infer_utterance_type_with_confidence(
        "철저한 조사를 부탁드립니다.", speaker_role="위원", position_type="의원"
    )
    assert utype == "statement"
    assert conf >= 0.80


def test_confidence_government_with_answer_marker_high():
    utype, conf = infer_utterance_type_with_confidence(
        "답변드리겠습니다. 검토 후 제출하겠습니다.",
        speaker_role="통일부장관", position_type="정부측"
    )
    assert utype == "answer"
    assert conf >= 0.88


def test_confidence_government_no_marker_medium():
    utype, conf = infer_utterance_type_with_confidence(
        "해당 정책은 지속적으로 진행 중입니다.",
        speaker_role="외교부장관", position_type="정부측"
    )
    assert utype == "answer"
    assert 0.65 <= conf < 0.90


def test_confidence_fallback_question_low():
    utype, conf = infer_utterance_type_with_confidence(
        "이 부분이 어떻게 진행되는지 궁금합니다.",
        speaker_role="위원", position_type="의원"
    )
    assert utype == "question"
    assert conf < 0.80


def test_infer_utterance_type_backward_compat():
    # 기존 infer_utterance_type은 그대로 str 반환
    result = infer_utterance_type(
        "어떤 대책을 갖고 있습니까?", speaker_role="위원", position_type="의원"
    )
    assert isinstance(result, str)
    assert result == "question"


def test_issue_score_zero_for_neutral():
    assert infer_issue_score("오늘 회의를 개의하겠습니다. 감사합니다.") == 0.0


def test_issue_score_strong_signals():
    score = infer_issue_score("예산 낭비와 비리 쟁점이 심각합니다.")
    assert score >= 0.50


def test_issue_score_numerical_complaint():
    score = infer_issue_score("3억 원이 낭비되었습니다.")
    assert score >= 0.20


def test_issue_score_member_question_bonus():
    base = infer_issue_score("우려됩니다.", utterance_type="statement", position_type="정부측")
    boosted = infer_issue_score("우려됩니다.", utterance_type="question", position_type="의원")
    assert boosted > base


def test_issue_score_capped_at_one():
    text = "쟁점 논란 갈등 비리 낭비 위반 문제가 있습니다 우려됩니다 지적받습니다 100억 원 낭비 즉각 조치"
    assert infer_issue_score(text) == 1.0


def test_issue_score_medium_signals():
    score = infer_issue_score("이 부분에 문제가 있습니다. 개선이 필요합니다.")
    assert 0.10 <= score <= 0.60


def test_importance_score_zero_for_procedural():
    assert infer_importance_score("오늘 회의를 개의하겠습니다.") == 0.0


def test_importance_score_commitment_signals():
    score = infer_importance_score("조속히 검토하겠습니다. 시행하겠습니다.")
    assert score >= 0.15


def test_importance_score_decision_marker():
    score = infer_importance_score("정부 입장을 말씀드리겠습니다.")
    assert score >= 0.20


def test_importance_score_govt_answer_bonus():
    base = infer_importance_score("노력하겠습니다.", utterance_type="statement", position_type="의원")
    boosted = infer_importance_score("노력하겠습니다.", utterance_type="answer", position_type="정부측")
    assert boosted > base


def test_importance_score_capped_at_one():
    text = "시행하겠습니다. 추진하겠습니다. 마련하겠습니다. 정부 입장을 밝힙니다. 장관으로서 공식적으로 답변드립니다."
    assert infer_importance_score(text, utterance_type="answer", position_type="정부측") == 1.0


def test_importance_score_member_question_bonus():
    base = infer_importance_score("정부 입장은?", utterance_type="statement", position_type="기타")
    boosted = infer_importance_score("정부 입장은?", utterance_type="question", position_type="의원")
    assert boosted > base


def test_extract_agency_known_agency():
    assert extract_agency_from_query("외교부가 재외국민 보호에 대해 뭐라 했나?") == "외교부"


def test_extract_agency_alias_mapping():
    assert extract_agency_from_query("국정원의 입장은?") == "국가정보원"


def test_extract_agency_new_agency():
    assert extract_agency_from_query("금융위원회의 답변을 알고 싶다") == "금융위원회"


def test_extract_agency_returns_none_for_no_match():
    assert extract_agency_from_query("일반적인 정책 질의") is None


def test_extract_agency_returns_none_for_empty():
    assert extract_agency_from_query("") is None


def test_extract_agency_first_match_wins():
    result = extract_agency_from_query("외교부와 통일부의 협력 방안")
    assert result == "외교부"
