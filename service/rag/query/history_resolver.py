"""멀티턴 히스토리 기반 지시어 해소.

이전 턴 질문에서 인물/주제 엔티티를 추출해, 현재 질문의 지시어(그 장관, 이 문제 등)를
구체적인 명칭으로 대체한다. Router/graph 호출 전 API 레이어에서 실행.
"""
from __future__ import annotations

import re

# 지시어 + 명사: "그 장관", "이 발언", "그분" 등
_BACK_REF = re.compile(
    r"(?:^|(?<=\s))(?:그|이|저)\s*(?:장관|의원|위원장|위원|차관|총장|원장|대표|의장|대통령|총리|사람|분|발언|정책|내용|이야기|주제|입장|주장|안건|법안|관련)"
    r"|방금|아까|앞서\s*(?:말한|언급한|나온|설명한)"
    r"|그\s*(?:외에도?|이후에?|다음에?|밖에도?)\s*(?:다른|추가|더)",
    re.UNICODE,
)

# 인물 패턴: "조태열 장관", "김석기 위원장" 등
_PERSON = re.compile(
    r"[가-힣]{2,4}\s*(?:장관|의원|위원장|위원|차관|총장|원장|대표|의장|대통령|총리)",
    re.UNICODE,
)

# 주제 키워드: 3자 이상 한글 (지시어·일반 접속사 제외)
_KEYWORD = re.compile(r"[가-힣]{3,}", re.UNICODE)

_STOPWORDS = {
    "관련해서", "대해서", "관련된", "대한해", "있나요", "있어요", "없나요", "없어요",
    "알려줘", "알려주세요", "해주세요", "해줘요", "무엇이", "어떻게", "어떤지",
    "발언한", "말했나", "언급한", "했나요", "하셨나", "인가요", "라고요",
}


def _has_back_ref(question: str) -> bool:
    return bool(_BACK_REF.search(question))


def _extract_entities(prev_q: str) -> list[str]:
    """이전 질문에서 인물/주제 엔티티를 최대 3개 추출."""
    # 인물명 우선
    persons = [m.group(0).replace(" ", "") for m in _PERSON.finditer(prev_q)]
    if persons:
        return persons[:2]
    # 인물 없으면 주제 키워드
    tokens = [t for t in _KEYWORD.findall(prev_q) if t not in _STOPWORDS]
    return tokens[:3]


def resolve(question: str, history: list[dict]) -> str:
    """지시어 해소: 현재 질문에 이전 턴 엔티티를 접두 주입.

    변경 없음 조건:
    - history가 비어 있거나 이전 user 턴 없음
    - 현재 질문에 지시어/후방 참조 없음
    - 추출된 엔티티가 이미 현재 질문에 포함됨
    """
    if not history or not _has_back_ref(question):
        return question

    prev_user_qs = [m["content"] for m in history if m.get("role") == "user"]
    if not prev_user_qs:
        return question

    entities = _extract_entities(prev_user_qs[-1])
    if not entities:
        return question

    new_entities = [e for e in entities if e not in question]
    if not new_entities:
        return question

    return " ".join(new_entities) + " " + question
