import logging
import re

from graph.state import QAState
from graph.utils.level import defaults
from service.rag.query.question_types import (
    apply_route_defaults,
    classify_question,
    get_question_type_spec,
)
from service.rag.retrieval.temporal_parser import NationalAssemblyTemporalParser
from service.office_aliases import match_office_alias, office_query_metadata

logger = logging.getLogger(__name__)

_temporal_parser = NationalAssemblyTemporalParser()

# 애매한 쿼리 감지
_MEANINGFUL_TOKEN = re.compile(r"[가-힣a-zA-Z]{2,}")
_PURE_DEICTIC = re.compile(
    r"^(?:이것|저것|그것|이거|저거|그거|이게|저게|그게|거기|여기|저기|"
    r"이건|저건|그건|이분|저분|그분|이\s*사람|그\s*사람|저\s*사람)\s*"
    r"(?:뭐야?|알려줘|해줘|설명해|뭔가요?|뭔지|뭐가요?)?\s*[?？]?$"
)


def _is_too_vague(question: str) -> bool:
    """의미 있는 정보가 부족한 질문 감지.
    4자 이상 복합어(대북정책, 한미동맹 등)는 유효 단독 질의로 허용.
    """
    q = question.strip()
    if not q or len(q) <= 2:
        return True
    if _PURE_DEICTIC.match(q):
        return True
    tokens = _MEANINGFUL_TOKEN.findall(q)
    if not tokens:
        return True
    # 단일 짧은 토큰(2자 이하)만 있으면 vague — 3자+ 단어는 도메인 키워드로 허용
    if len(tokens) == 1 and len(tokens[0]) <= 2:
        return True
    return False


def _build_clarification_message() -> str:
    return (
        "질문이 너무 간략하거나 검색 대상이 명확하지 않습니다.\n\n"
        "다음과 같이 구체적으로 질문해 주시면 정확한 답변이 가능합니다.\n\n"
        "**포함하면 좋은 정보**\n"
        "- 인물 이름 또는 직함 (예: 조태열 장관, 김석기 위원장)\n"
        "- 주제 키워드 (예: 대북정책, 한미동맹, 방위비분담, 공정거래)\n"
        "- 시기 (예: 2024년 국감, 올해 2월)\n\n"
        "**질문 예시**\n"
        "- \"조태열 장관이 한미동맹에 대해 발언한 내용이 있나요?\"\n"
        "- \"2024년 국감에서 대북정책 관련 여야 입장 차이는?\"\n"
        "- \"방송통신위원장이 공영방송 독립성에 대해 어떤 입장인가요?\""
    )

# 질문에 특정 문서·보고서 이름이 포함됐는지 감지
_DOC_NAME_PATTERN = re.compile(
    "[‘’“”「」'\"]"  # 따옴표류
    r"|"
    r"(?:보고서|로드맵|백서|계획서|협약서|합의문|성명서|선언문|결의문)"
)

# 집계형 쿼리 감지: "어떤 의원들이 X를 주장했나", "위원들이 공통적으로" 등
# 특정 화자가 아니라 여러 화자를 집계하는 쿼리 → balance_speakers + top_k 증가
_AGGREGATION_PATTERNS = re.compile(
    r"(?:어떤|어느|각|모든)\s*(?:의원|위원|정치인)들?"
    r"|(?:의원|위원)들이\s*(?:공통|제기|주장|지적|요구|발언|어떻게|무엇을|어떤)"
    r"|(?:의원|위원)들은\s*(?:어떻게|왜|무엇을|어떤|서로)"
    r"|공통적으로\s*(?:제기|주장|지적|요구)",
)

# 여야 비교 쿼리 감지
_PARTY_COMPARE_DIRECT = re.compile(
    r"여야|여당과\s*야당|야당과\s*여당"
)
_PARTY_NAMES = re.compile(
    r"더불어민주당|민주당|국민의힘|조국혁신당"
)
_COMPARISON_VERBS = re.compile(
    r"비교|차이|다르|달리|대조|입장\s*차|갈리|맞서|충돌|대립"
)

# 단독 발언자 질문 감지: 직함+이름 또는 이름+직함 패턴
# P1/P3에서 이름 자리를 {2,3}으로 제한 — 한국 인명은 2-3자이며,
# {2,4}는 조사("은/는/이/가")나 수식어("여야","여러")까지 캡처해 오탐 유발
_SPEAKER_UNIT = re.compile(
    # P1: 직함 + 이름 순서 (예: "위원장 김석기") — 이름 2-3자 한정
    r"(?:장관|의원|위원장|위원(?!회)|차관|총장|원장|대표|의장)\s+[가-힣]{2,3}"
    r"|"
    # P2: 이름 + 전/현[직] + [부처]직함 (예: "조태열 전 외교부장관")
    r"[가-힣]{2,4}\s+(?:전|현|전직|현직)\s+(?:[가-힣]+부\s*)?(?:장관|의원|위원장|위원(?!회)|차관|총장|원장|대표|의장)"
    r"|"
    # P3: [이름\s+]?[부처]?직함 (예: "조태열 장관", "외교부장관") — 이름 2-3자 한정
    # (?<![가-힣]): 이름 슬롯이 단어 중간(예: "국민의힘"의 "의힘")에서 시작하지 않도록 부정 후방탐색
    # 위원(?!회): "위원회"의 일부를 화자 직함으로 오탐하지 않도록 부정 전방탐색
    r"(?:(?<![가-힣])[가-힣]{2,3}\s+)?(?:[가-힣]+부\s*)?(?:장관|의원|위원장|위원(?!회)|차관|총장|원장|대표|의장)"
)

# 발언자 인명 검증용 상수
_NON_NAME_KW = frozenset({
    "장관", "의원", "위원장", "위원", "차관", "총장", "원장", "대표", "의장",
    "소위원장", "수석", "처장", "국장", "사무총장", "후보자", "후보",
})
_ORG_SUFFIX = ("부", "처", "청")
_COMMON_NON_NAME = frozenset({
    "여야", "여당", "야당", "여러", "일부", "많은", "일각",
    "어떤", "어느", "모든", "아무",  # 지시 한정사 — 인명 오탐 방지
})
_PARTICLE_ENDINGS = ("은", "는", "이", "가", "를", "을", "의", "에", "서", "로", "며", "다", "고", "지")


def _is_valid_person_name_kw(kw_list: list[str]) -> bool:
    """키워드 목록에 실제 인명이 포함되어 있는지 확인.
    직함어·조사·수식어·정당명 등을 제외하고 2-3자 인명이 남는지 검사한다.
    """
    for kw in kw_list:
        if kw in _NON_NAME_KW:
            continue
        if kw in _COMMON_NON_NAME:
            continue
        if any(kw.endswith(s) for s in _ORG_SUFFIX):
            continue
        if any(kw.endswith(p) for p in _PARTICLE_ENDINGS):
            continue
        if len(kw) > 3:  # 4자 이상은 조사·부처명 혼입 가능성 높음
            continue
        if len(kw) >= 2:
            return True
    return False


def _is_party_comparison_query(question: str) -> bool:
    """여야 비교 의도가 있는 쿼리인지 감지."""
    if _PARTY_COMPARE_DIRECT.search(question):
        return True
    if len(set(_PARTY_NAMES.findall(question))) >= 2:
        return True
    if ("야당" in question or "여당" in question) and _COMPARISON_VERBS.search(question):
        return True
    return False


def _extract_query_speaker_kw(question: str) -> list[str]:
    """단독 발언자 질문에서 발언 주체 키워드 추출.
    0개(발언 주체 없음)나 2개 이상(비교 질문)이면 빈 목록 반환.
    인명 검증 실패 시(수식어·조사·정당명 등)도 빈 목록 반환.
    """
    matches = [m.group(0) for m in _SPEAKER_UNIT.finditer(question)]
    if len(matches) != 1:
        return []
    kws = [t for t in re.findall(r"[가-힣]{2,}", matches[0])]
    if not _is_valid_person_name_kw(kws):
        return []
    return kws


def _extract_comparison_subjects(question: str) -> list[list[str]]:
    """비교 질문(정확히 2명)에서 각 주체의 키워드 목록 반환.
    예: "조태열 장관과 정동영 장관" → [["조태열", "장관"], ["정동영", "장관"]]
    두 주체 중 하나라도 인명 검증에 실패하면 빈 목록 반환.
    """
    matches = [m.group(0) for m in _SPEAKER_UNIT.finditer(question)]
    if len(matches) != 2:
        return []
    subjects = [[t for t in re.findall(r"[가-힣]{2,}", m)] for m in matches]
    if not all(_is_valid_person_name_kw(s) for s in subjects):
        return []
    return subjects


def run(state: QAState) -> QAState:
    """
    기본 검색 메타(top_k, alpha 등)를 깔고, 호출 시 넘긴 meta로 덮어쓴다.
    질문에 특정 문서명이 감지되면 doc_name_query 플래그를 설정한다.
    질문 유형을 question_type으로 분류하고, 단독 발언자 질문이면 query_speaker_kw,
    비교 질문이면 query_comparison_subjects를 설정한다.
    """
    logger.info("Router start")
    incoming = state.get("meta")
    incoming = incoming if isinstance(incoming, dict) else {}
    state["meta"] = {**defaults(), **incoming}

    question = state.get("question", "")

    # 애매한 쿼리 감지 — 명확화 메시지 요청
    if question and _is_too_vague(question):
        state["meta"]["needs_clarification"] = True
        state["meta"]["clarification_message"] = _build_clarification_message()
        logger.info("Router: too_vague query detected → needs_clarification")
        return state

    if question and _DOC_NAME_PATTERN.search(question):
        state["meta"]["doc_name_query"] = True
        logger.info("Router: doc_name_query detected")

    if question:
        question_type = classify_question(question)
        state["meta"] = apply_route_defaults(state["meta"], question_type, force_question_type=True)
        spec = get_question_type_spec(question_type)
        logger.info("Router: question_type=%s(%s)", spec.id, spec.label)

        speaker_kw = _extract_query_speaker_kw(question)
        if speaker_kw:
            state["meta"]["query_speaker_kw"] = speaker_kw
            logger.info("Router: query_speaker_kw=%s", speaker_kw)
        else:
            comparison = _extract_comparison_subjects(question)
            if comparison:
                state["meta"]["query_comparison_subjects"] = comparison
                logger.info("Router: query_comparison_subjects=%s", comparison)

        office_key = match_office_alias(question)
        if office_key:
            state["meta"].update(office_query_metadata(office_key))
            state["meta"]["require_speaker"] = True
            logger.info("Router: query_office_kw=%s", office_key)

        # 집계형 쿼리 감지 → balance_speakers 활성화 + top_k 확대
        # 특정 화자 없이 여러 의원/위원의 의견을 묻는 쿼리
        if not state["meta"].get("aggregate_query") and _AGGREGATION_PATTERNS.search(question):
            state["meta"]["aggregate_query"] = True
            if not state["meta"].get("balance_speakers"):
                state["meta"]["balance_speakers"] = True
            if state["meta"].get("top_k", 5) < 8:
                state["meta"]["top_k"] = 8
            logger.info("Router: aggregate_query detected → balance_speakers=True, top_k≥8")

        # 여야 비교 쿼리 감지 → balance_speakers 자동 활성화
        # UI에서 이미 켠 경우엔 그대로 유지
        if not state["meta"].get("balance_speakers") and _is_party_comparison_query(question):
            state["meta"] = apply_route_defaults(state["meta"], "comparison", force_question_type=True)
            logger.info("Router: party_comparison detected → balance_speakers=True")

        # 쿼리에서 날짜 범위 추출 — UI에서 이미 명시한 경우엔 덮어쓰지 않음
        if not state["meta"].get("date_from") and not state["meta"].get("date_to"):
            date_from, date_to = _temporal_parser.parse(question)
            if date_from:
                state["meta"]["date_from"] = date_from
                state["meta"]["date_to"] = date_to or date_from
                logger.info("Router: temporal date_from=%s date_to=%s", date_from, date_to)

    logger.info("Router complete → meta=%s", state.get("meta"))
    return state
