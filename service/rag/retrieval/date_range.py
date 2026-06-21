"""회의일 문자열 필터 정규화 (메타 데이터 형식이 YYYY-MM-DD일 때 문자열 비교로 순서 판단)."""


def normalize_meeting_date_range(
    date_from: str | None,
    date_to: str | None,
) -> tuple[str | None, str | None]:
    """
    빈 값은 필터 없음으로 간주.
    시작일이 종료일보다 뒤(사용자 입력 오류)면 두 값을 맞바꿔 비어 보이는 결과를 줄인다.
    """
    a = (date_from or "").strip() or None
    b = (date_to or "").strip() or None
    if not a or not b:
        return a, b
    if a > b:
        return b, a
    return a, b
