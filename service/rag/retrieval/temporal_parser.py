from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional


class NationalAssemblyTemporalParser:
    """국회 회의록 쿼리에서 날짜 범위를 추출해 date_from / date_to (YYYYMMDD)를 반환."""

    def __init__(self):
        self._now = datetime.now()

    def parse(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """
        우선순위: 연도+월 > 연도(상/하반기 포함) > 상대 표현
        감지 불가 시 (None, None) 반환.
        """
        result = self._parse_year_month(query)
        if result[0]:
            return result

        result = self._parse_year_only(query)
        if result[0]:
            return result

        return self._parse_relative(query)

    # ── 명시적 연도 + 월 ─────────────────────────────────────────────
    def _parse_year_month(self, query: str) -> tuple[Optional[str], Optional[str]]:
        m = re.search(r"(20\d{2})\s*년\s*([1-9]|1[0-2])\s*월", query)
        if not m:
            return None, None
        year, month = int(m.group(1)), int(m.group(2))
        last = self._month_last_day(year, month)
        return f"{year}{month:02d}01", f"{year}{month:02d}{last:02d}"

    # ── 명시적 연도 (상/하반기 포함) ─────────────────────────────────
    def _parse_year_only(self, query: str) -> tuple[Optional[str], Optional[str]]:
        m = re.search(r"(20\d{2})\s*년", query)
        if not m:
            return None, None
        year = int(m.group(1))
        if "상반기" in query:
            return f"{year}0101", f"{year}0630"
        if "하반기" in query:
            return f"{year}0701", f"{year}1231"
        return f"{year}0101", f"{year}1231"

    # ── 상대적 표현 ───────────────────────────────────────────────────
    def _parse_relative(self, query: str) -> tuple[Optional[str], Optional[str]]:
        now = self._now

        if re.search(r"올해|금년", query):
            return f"{now.year}0101", f"{now.year}1231"

        if re.search(r"작년|전년|지난해", query):
            y = now.year - 1
            return f"{y}0101", f"{y}1231"

        m = re.search(r"최근\s*(\d+)\s*년", query)
        if m:
            n = int(m.group(1))
            return f"{now.year - n + 1}0101", f"{now.year}1231"

        # "최근" 단독 → 최근 6개월
        if re.search(r"최근|요즘|근래", query):
            start = now - timedelta(days=180)
            return start.strftime("%Y%m%d"), now.strftime("%Y%m%d")

        return None, None

    # ── 유틸 ─────────────────────────────────────────────────────────
    @staticmethod
    def _month_last_day(year: int, month: int) -> int:
        if month == 12:
            return 31
        if month in (4, 6, 9, 11):
            return 30
        if month == 2:
            return 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
        return 31
