import logging
import re

from graph.state import QAState
from graph.utils.level import defaults

logger = logging.getLogger(__name__)

# 질문에 특정 문서·보고서 이름이 포함됐는지 감지
_DOC_NAME_PATTERN = re.compile(
    "[‘’“”「」'\"]"  # 따옴표류
    r"|"
    r"(?:보고서|로드맵|백서|계획서|협약서|합의문|성명서|선언문|결의문)"
)

# 단독 발언자 질문 감지: 직함+이름 또는 이름+직함 패턴
_SPEAKER_UNIT = re.compile(
    # 직함 + 이름 순서 (예: "위원장 김석기")
    r"(?:장관|의원|위원장|위원|차관|총장|원장|대표|의장)\s+[가-힣]{2,4}"
    r"|"
    # 이름/부처 + 직함 순서 (예: "통일부 장관", "조태열 장관")
    r"(?:[가-힣]{2,4}\s+)?(?:[가-힣]+부\s*)?(?:장관|의원|위원장|위원|차관|총장|원장|대표|의장)"
)


def _extract_query_speaker_kw(question: str) -> list[str]:
    """단독 발언자 질문에서 발언 주체 키워드 추출.
    0개(발언 주체 없음)나 2개 이상(비교 질문)이면 빈 목록 반환.
    """
    matches = [m.group(0) for m in _SPEAKER_UNIT.finditer(question)]
    if len(matches) != 1:
        return []
    return [t for t in re.findall(r"[가-힣]{2,}", matches[0])]


def _extract_comparison_subjects(question: str) -> list[list[str]]:
    """비교 질문(정확히 2명)에서 각 주체의 키워드 목록 반환.
    예: "조태열 장관과 정동영 장관" → [["조태열", "장관"], ["정동영", "장관"]]
    """
    matches = [m.group(0) for m in _SPEAKER_UNIT.finditer(question)]
    if len(matches) != 2:
        return []
    return [[t for t in re.findall(r"[가-힣]{2,}", m)] for m in matches]


def run(state: QAState) -> QAState:
    """
    기본 검색 메타(top_k, alpha 등)를 깔고, 호출 시 넘긴 meta로 덮어쓴다.
    질문에 특정 문서명이 감지되면 doc_name_query 플래그를 설정한다.
    단독 발언자 질문이면 query_speaker_kw, 비교 질문이면 query_comparison_subjects를 설정한다.
    """
    logger.info("Router start")
    incoming = state.get("meta")
    incoming = incoming if isinstance(incoming, dict) else {}
    state["meta"] = {**defaults(), **incoming}

    question = state.get("question", "")
    if question and _DOC_NAME_PATTERN.search(question):
        state["meta"]["doc_name_query"] = True
        logger.info("Router: doc_name_query detected")

    if question:
        speaker_kw = _extract_query_speaker_kw(question)
        if speaker_kw:
            state["meta"]["query_speaker_kw"] = speaker_kw
            logger.info("Router: query_speaker_kw=%s", speaker_kw)
        else:
            comparison = _extract_comparison_subjects(question)
            if comparison:
                state["meta"]["query_comparison_subjects"] = comparison
                logger.info("Router: query_comparison_subjects=%s", comparison)

    logger.info("Router complete → meta=%s", state.get("meta"))
    return state
