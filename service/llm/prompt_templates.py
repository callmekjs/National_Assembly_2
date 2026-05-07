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
      "답변 끝에 [ref: source_id, date] 형식의 근거를 포함한다.\n"
    )
    return base + "\n" + PROMPT_TEMPLATES.get(level, PROMPT_TEMPLATES["beginner"])

def build_user_prompt(question: str, context: str, level: str) -> str:
    if level == "beginner":
        structure = "①핵심 요약(쉬운 용어) ②간단 예시 ③근거"
    elif level == "advanced":
        structure = "①핵심 결론 ②수치 비교/추세 해석 ③리스크·가정 ④근거"
    else:
        structure = "①핵심 요약 ②핵심 수치·포인트 ③근거"
    return f"질문: {question}\n\n[컨텍스트]\n{context}\n\n요구 형식: {structure}"

