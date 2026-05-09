from __future__ import annotations

import os
import re
from typing import Any

import requests


class Generator:
    def _build_citations(self, retrieved: list[dict[str, Any]], max_items: int = 5) -> str:
        lines: list[str] = []
        for idx, item in enumerate(retrieved[:max_items], start=1):
            source_id = item.get("source_id", "")
            date = item.get("date", "")
            quote = (item.get("content", "") or "").replace("\n", " ").strip()[:140]
            lines.append(f"[{idx}] source={source_id} date={date} quote={quote}")
        return "\n".join(lines)

    def _sanitize_invalid_citations(self, answer: str, max_ref: int) -> str:
        if not answer or max_ref <= 0:
            return answer

        def _replace(match: re.Match[str]) -> str:
            ref_no = int(match.group(1))
            return match.group(0) if 1 <= ref_no <= max_ref else ""

        cleaned = re.sub(r"\[(\d+)\]", _replace, answer)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    def _generate_with_openai(self, question: str, context: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return ""

        payload = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 국회 회의록 분석 도우미다. 반드시 근거 기반으로 간결하게 답하라.",
                },
                {
                    "role": "user",
                    "content": f"질문:\n{question}\n\n참고문서:\n{context}\n\n요구사항: 핵심 3줄 이내 + 마지막 줄에 근거 번호([1],[2]...) 표기",
                },
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            return ""

    def generate(self, question: str, context: str) -> str:
        if not context.strip():
            return "관련 문서를 찾지 못했습니다."
        ai_answer = self._generate_with_openai(question, context)
        if ai_answer:
            return ai_answer
        return f"질문: {question}\n\n근거 요약:\n{context[:1200]}"

    def generate_with_citations(self, question: str, retrieved: list[dict[str, Any]]) -> str:
        if not retrieved:
            return "관련 문서를 찾지 못했습니다."
        max_ref = min(5, len(retrieved))
        context = "\n\n".join(
            f"[{i+1}] source={r.get('source_id','')} date={r.get('date','')}\n{(r.get('content','') or '')[:800]}"
            for i, r in enumerate(retrieved[:5])
        )
        answer = self._sanitize_invalid_citations(self.generate(question, context), max_ref)
        citations = self._build_citations(retrieved, max_items=max_ref)
        return f"{answer}\n\n근거:\n{citations}"
