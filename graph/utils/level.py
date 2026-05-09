"""user_level별 기본 검색 메타(Streamlit 초기값과 정합).

Router는 이 값 위에 호출 단계에서 넘긴 meta 키를 덮어씁니다."""

from __future__ import annotations

from typing import Any


def defaults(level: str) -> dict[str, Any]:
    _ = level  # 초기값은 레벨과 무관(필요 시 레벨별 분기 가능)
    return {
        "top_k": 8,
        "alpha": 0.75,
        "committee": "외교통일위원회",
        "date_from": "",
        "date_to": "",
        "use_reranker": False,
        "balance_speakers": False,
        "candidate_multiplier": 50,
    }
