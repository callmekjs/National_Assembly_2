"""기본 검색 메타(Streamlit 초기값과 정합).

Router는 이 값 위에 호출 단계에서 넘긴 meta 키를 덮어씁니다."""

from __future__ import annotations

from typing import Any


def defaults() -> dict[str, Any]:
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
