"""정무위원회 + 과학기술정보방송통신위원회 22대 회의록 PDF 일괄 수집."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.crawling.assembly_crawler import download_committee

# 과학기술정보방송통신위원회: menuNo=600238 (스크린샷 URL에서 확인)
# 정무위원회: menuNo 미확인 → menuNo 단독 조회 → committeeCd 탐색 순으로 시도
COMMITTEES = [
    "과학기술정보방송통신위원회",
    "정무위원회",
]

if __name__ == "__main__":
    for name in COMMITTEES:
        download_committee(
            committee_name=name,
            title_keyword="제22대",
            max_files=None,
        )
    print("\n전체 완료.")
