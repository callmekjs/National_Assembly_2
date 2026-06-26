from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuestionTypeSpec:
    id: str
    label: str
    description: str
    answer_mode: str
    min_top_k: int


QUESTION_TYPES: dict[str, QuestionTypeSpec] = {
    "topic_search": QuestionTypeSpec(
        id="topic_search",
        label="특정 주제 발언 검색",
        description="주제·키워드와 관련된 발언을 찾는다.",
        answer_mode="topic",
        min_top_k=8,
    ),
    "speaker_search": QuestionTypeSpec(
        id="speaker_search",
        label="특정 의원/인물 발언 검색",
        description="특정 발언자의 직접 발언과 입장을 찾는다.",
        answer_mode="speaker",
        min_top_k=8,
    ),
    "meeting_summary": QuestionTypeSpec(
        id="meeting_summary",
        label="회의록 요약",
        description="특정 회의 또는 기간의 흐름과 핵심 내용을 요약한다.",
        answer_mode="summary",
        min_top_k=12,
    ),
    "qa_pair_extract": QuestionTypeSpec(
        id="qa_pair_extract",
        label="질의-답변 쌍 정리",
        description="위원 질의와 정부·기관 답변을 짝지어 정리한다.",
        answer_mode="qa_pairs",
        min_top_k=12,
    ),
    "issue_extract": QuestionTypeSpec(
        id="issue_extract",
        label="쟁점 정리",
        description="회의에서 반복된 쟁점·우려·논점을 추출한다.",
        answer_mode="issues",
        min_top_k=10,
    ),
    "question_draft": QuestionTypeSpec(
        id="question_draft",
        label="국감/상임위 질의서 작성",
        description="회의록 근거를 바탕으로 질의서나 질문 초안을 만든다.",
        answer_mode="draft",
        min_top_k=10,
    ),
    "agency_answer_tracking": QuestionTypeSpec(
        id="agency_answer_tracking",
        label="기관/부처 답변 추적",
        description="기관 답변, 후속 조치, 자료 제출, 이행 여부를 추적한다.",
        answer_mode="agency_tracking",
        min_top_k=12,
    ),
    "comparison": QuestionTypeSpec(
        id="comparison",
        label="과거-현재 발언 비교",
        description="인물·정당·시점별 발언 변화와 차이를 비교한다.",
        answer_mode="comparison",
        min_top_k=10,
    ),
    "source_check": QuestionTypeSpec(
        id="source_check",
        label="원문/출처 확인",
        description="근거 발언의 회의일, 발언자, 페이지, 원문 출처를 확인한다.",
        answer_mode="source_check",
        min_top_k=5,
    ),
    "report_generation": QuestionTypeSpec(
        id="report_generation",
        label="보고서/브리핑 생성",
        description="검색된 회의록 근거를 묶어 보고서나 브리핑 형태로 작성한다.",
        answer_mode="report",
        min_top_k=12,
    ),
}

QUESTION_TYPE_ORDER: tuple[str, ...] = tuple(QUESTION_TYPES.keys())

_CLASSIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("source_check", re.compile(r"출처|원문|근거|인용|페이지|몇\s*쪽|회의록\s*확인|어디에\s*나와")),
    ("question_draft", re.compile(r"질의서|질문\s*초안|질의\s*작성|국감\s*질의|상임위\s*질의|물어볼\s*질문|질문\s*만들")),
    ("qa_pair_extract", re.compile(r"질의[-\s]*답변|질문[-\s]*답변|문답|질답|Q\s*&\s*A|Q&A|답변\s*쌍")),
    ("agency_answer_tracking", re.compile(r"기관|부처|정부\s*답변|답변\s*추적|후속\s*조치|자료\s*제출|이행|조치\s*상황")),
    ("comparison", re.compile(r"비교|차이|대조|변화|달라졌|과거|현재|이전|최근|전후|입장\s*차|여야")),
    ("issue_extract", re.compile(r"쟁점|이슈|논란|문제점|우려|갈등|핵심\s*논점|논점|비판|지적\s*사항")),
    ("meeting_summary", re.compile(r"회의록?\s*요약|회의\s*요약|전체\s*요약|핵심\s*내용|요약해|정리해|흐름")),
    ("report_generation", re.compile(r"보고서|브리핑|리포트|분석\s*글|자료\s*만들|문서\s*작성|정책\s*메모")),
    ("speaker_search", re.compile(r"[가-힣]{2,4}\s*(?:의원|위원|장관|차관|위원장|대표|총장|원장|청장)|(?:의원|위원|장관|차관|위원장)\s+[가-힣]{2,4}")),
    ("topic_search", re.compile(r"검색|찾아|언급|다룬|발언|주제|내용")),
)

_GOVT_ROLE_KEYWORDS = (
    "장관",
    "차관",
    "차장",
    "청장",
    "국장",
    "실장",
    "본부장",
    "대사",
    "과장",
    "조정관",
    "대변인",
    "비서관",
)

_QUESTION_MARKERS = re.compile(r"\?|질문|질의|묻|여쭙|확인하고\s*싶|어떻게|왜|무엇|언제|누구|입장입니까|맞습니까|아닙니까")
_ANSWER_MARKERS = re.compile(r"답변드|말씀드리|보고드리|설명드리|확인해\s*보|검토하|조치하|추진하|제출하|협의하")
_PROCEDURAL_MARKERS = re.compile(r"개의|산회|정회|속개|의사일정|상정|선임|발언해\s*주십시오|질의해\s*주시")
_ISSUE_MARKERS = re.compile(r"쟁점|문제|우려|논란|갈등|비판|지적|개선|대책|필요|부족|위험|책임")

# 한국어 질의 종결 패턴 — 문장 끝에 등장하는 실제 질의 어미/요청어
_QUESTION_ENDINGS = re.compile(
    r"(습니까|입니까|인가요|나요|않습니까|없습니까|됩니까|되나요|되십니까"
    r"|어떻습니까|어떠합니까|어떤가요|어떻게\s*보십니까|어떻게\s*생각하십니까"
    r"|해주십시오|해주시겠습니까|해주시기\s*바랍니다|주시기\s*바랍니다"
    r"|부탁드립니다|부탁합니다|요청합니다|요청드립니다"
    r"|말씀해\s*주|알려주십시오|설명해\s*주|확인해\s*주|검토해\s*주"
    r"|밝혀주십시오|답해\s*주십시오|\?|？)"
)

# 의원 의사진행·마무리 발언 패턴 (질의가 아님)
_MEMBER_PROCEDURAL = re.compile(
    r"^(이상입니다|이상으로|감사합니다|고맙습니다|수고하셨습니다"
    r"|다음으로|마치겠습니다|끝내겠습니다|충분합니다|알겠습니다"
    r"|시간이\s*다|시간\s*관계상)"
)

_AGENCY_ALIASES: tuple[tuple[str, str], ...] = (
    ("외교부", "외교부"),
    ("통일부", "통일부"),
    ("국방부", "국방부"),
    ("기획재정부", "기획재정부"),
    ("법무부", "법무부"),
    ("행정안전부", "행정안전부"),
    ("대통령실", "대통령실"),
    ("국정원", "국가정보원"),
    ("국가정보원", "국가정보원"),
    ("방위사업청", "방위사업청"),
    ("경찰청", "경찰청"),
    ("소방청", "소방청"),
)

_UNIVERSAL_HINTS = {"topic_search", "source_check", "report_generation"}
_EMBED_HINT_EXCLUDES = _UNIVERSAL_HINTS | {"speaker_search", "comparison", "meeting_summary"}


def get_question_type_spec(question_type: str | None) -> QuestionTypeSpec:
    return QUESTION_TYPES.get(question_type or "", QUESTION_TYPES["topic_search"])


def classify_question(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "topic_search"
    for question_type, pattern in _CLASSIFIER_PATTERNS:
        if pattern.search(q):
            return question_type
    return "topic_search"


def route_defaults(question_type: str) -> dict[str, Any]:
    spec = get_question_type_spec(question_type)
    defaults: dict[str, Any] = {
        "question_type": spec.id,
        "question_type_label": spec.label,
        "answer_mode": spec.answer_mode,
        "min_top_k": spec.min_top_k,
    }
    if spec.id in {"comparison"}:
        defaults["balance_speakers"] = True
    if spec.id in {"speaker_search"}:
        defaults["require_speaker"] = True
    if spec.id in {"meeting_summary", "qa_pair_extract", "report_generation"}:
        defaults["use_parent_doc"] = True
        defaults["parent_doc_window"] = 1
    if spec.id in {"issue_extract", "question_draft", "agency_answer_tracking"}:
        defaults["candidate_multiplier"] = 80
    if spec.id in {"qa_pair_extract", "issue_extract", "question_draft", "agency_answer_tracking"}:
        defaults["question_type_filter"] = spec.id
    return defaults


def apply_route_defaults(meta: dict[str, Any], question_type: str, force_question_type: bool = False) -> dict[str, Any]:
    routed = dict(meta)
    defaults = route_defaults(question_type)
    current_top_k = int(routed.get("top_k") or 0)
    routed["top_k"] = max(current_top_k, int(defaults.pop("min_top_k")))
    current_multiplier = int(routed.get("candidate_multiplier") or 0)
    if "candidate_multiplier" in defaults:
        routed["candidate_multiplier"] = max(current_multiplier, int(defaults.pop("candidate_multiplier")))
    for key, value in defaults.items():
        if force_question_type and key in {"question_type", "question_type_label", "answer_mode"}:
            routed[key] = value
        elif isinstance(value, bool):
            routed[key] = bool(routed.get(key)) or value
        elif key not in routed or routed.get(key) in ("", None):
            routed[key] = value
    return routed


def infer_agency(speaker_role: str, text: str = "") -> str:
    blob = f"{speaker_role or ''} {text or ''}"
    for token, agency in _AGENCY_ALIASES:
        if token in blob:
            return agency
    return ""


def is_government_role(speaker_role: str) -> bool:
    return any(keyword in (speaker_role or "") for keyword in _GOVT_ROLE_KEYWORDS)


def infer_utterance_type(text: str, speaker_role: str = "", position_type: str = "") -> str:
    body = (text or "").strip()
    role = speaker_role or ""

    # ── 의사진행 (위원장) ──────────────────────────────────────
    if "위원장" in role and _PROCEDURAL_MARKERS.search(body[:200]):
        return "procedural"

    # ── 정부측 / 후보자 ───────────────────────────────────────
    if position_type in {"정부측", "후보자"} or is_government_role(role):
        # 질의 패턴만 있고 답변 패턴이 없으면 → 반문/설명
        if _QUESTION_MARKERS.search(body) and not _ANSWER_MARKERS.search(body):
            return "statement"
        return "answer"

    # ── 의원 발언 ──────────────────────────────────────────────
    # 1. 발언 마무리·의사진행 표현이 시작에 있으면 procedural
    if _MEMBER_PROCEDURAL.search(body[:60]):
        return "procedural"

    # 2. 발언 끝부분(마지막 400자)에 질의 종결 어미가 있으면 question
    #    → 앞부분에 설명이 길어도 마지막에 질문이 있으면 올바르게 분류
    tail = body[-400:] if len(body) > 400 else body
    if _QUESTION_ENDINGS.search(tail):
        return "question"

    # 3. 본문 어딘가에 기존 질의 마커가 있으면 question (fallback)
    if _QUESTION_MARKERS.search(body):
        return "question"

    return "statement"


def infer_chunk_question_type_hints(
    text: str,
    speaker: str = "",
    speaker_role: str = "",
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    meta = metadata or {}
    body = text or ""
    position_type = str(meta.get("position_type") or "")
    utterance_type = str(meta.get("utterance_type") or infer_utterance_type(body, speaker_role, position_type))
    agency = str(meta.get("agency") or infer_agency(speaker_role, body))

    hints = set(_UNIVERSAL_HINTS)
    if len(body) >= 240:
        hints.add("meeting_summary")
    if speaker:
        hints.update({"speaker_search", "comparison"})
    if utterance_type in {"question", "answer"}:
        hints.add("qa_pair_extract")
    if utterance_type == "question" and position_type in {"의원", "위원장", ""}:
        hints.add("question_draft")
    if agency or position_type in {"정부측", "후보자"}:
        hints.add("agency_answer_tracking")
    if _ISSUE_MARKERS.search(body):
        hints.add("issue_extract")
    return [question_type for question_type in QUESTION_TYPE_ORDER if question_type in hints]


def embed_hint_labels(hints: list[str]) -> list[str]:
    labels: list[str] = []
    for hint in hints:
        if hint in _EMBED_HINT_EXCLUDES:
            continue
        labels.append(get_question_type_spec(hint).label)
    return labels
