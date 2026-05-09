PROMPT_TEMPLATES = {
  "beginner": """
  사용자는 회의록 분석 초보자입니다.
  어려운 용어를 줄이고 쉽게 설명하세요.
  """,
  "intermediate": """
  사용자는 회의록 문맥을 이해할 수 있습니다.
  핵심 발언과 쟁점을 간결하게 정리하세요.
  """,
  "advanced": """
  사용자는 정책 맥락 분석을 원합니다.
  쟁점 비교와 흐름 해석, 근거 문장을 함께 제시하세요.
  """
}

def build_system_prompt(level: str) -> str:
    base = (
      "너는 국회 회의록 분석 Q&A 보조원이다. 제공 컨텍스트 밖 추론을 금지한다.\n"
      "날짜와 발언 내용은 원문 근거로 정확히 제시한다.\n"
      "답변 본문에는 반드시 [n] 인용 번호만 사용한다 (예: [1], [2]).\n"
      "인용 번호는 제공된 참고 문서 번호만 사용하고, 없는 번호를 만들지 않는다.\n"
    )
    return base + "\n" + PROMPT_TEMPLATES.get(level, PROMPT_TEMPLATES["beginner"])

def build_user_prompt(question: str, context: str, level: str) -> str:
    if level == "beginner":
        structure = "①핵심 요약(쉬운 용어) ②간단 예시 ③근거"
    elif level == "advanced":
        structure = "①핵심 결론 ②수치 비교/추세 해석 ③리스크·가정 ④근거"
    else:
        structure = "①핵심 요약 ②핵심 수치·포인트 ③근거"
    return (
        f"질문: {question}\n\n"
        f"[컨텍스트]\n{context}\n\n"
        "인용 규칙:\n"
        "- 본문에서 주장마다 [n] 형식 인용 번호를 붙일 것\n"
        "- [n]은 [참고 문서] 섹션에 있는 번호와 반드시 일치할 것\n"
        "- [ref: ...] 같은 다른 인용 형식은 금지\n\n"
        f"요구 형식: {structure}"
    )

