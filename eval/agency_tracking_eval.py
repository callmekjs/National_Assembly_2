"""
기관 답변 추적 알고리즘 평가

사용법:
    python eval/agency_tracking_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

sys.path.insert(0, str(ROOT))

from service.rag.query.question_types import extract_agency_from_query

MAX_CHUNKS = 2000

TEST_QUERIES = [
    "외교부가 재외국민 보호 정책에 대해 뭐라 했나?",
    "국방부는 병력 감축 계획을 어떻게 설명했나?",
    "기획재정부의 예산안 입장은 무엇인가?",
    "보건복지부가 의료 개혁에 대해 뭐라 했나?",
    "환경부의 탄소중립 정책 답변은?",
    "경찰청 수사권 조정에 관한 입장",
    "교육부가 교육 예산에 대해 설명한 내용",
]


def load_chunks(max_n: int = MAX_CHUNKS) -> list[dict]:
    chunks = []
    if not CHUNKS_FILE.exists():
        print(f"청크 파일 없음: {CHUNKS_FILE}")
        return chunks
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            chunks.append(json.loads(line))
            if len(chunks) >= max_n:
                break
    return chunks


def agency_distribution(chunks: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for c in chunks:
        ag = (c.get("metadata") or {}).get("agency", "") or ""
        if ag:
            dist[ag] = dist.get(ag, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def answer_by_agency(chunks: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for c in chunks:
        meta = c.get("metadata") or {}
        if meta.get("utterance_type") == "answer" and meta.get("agency"):
            ag = meta["agency"]
            dist[ag] = dist.get(ag, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def top_agency_answers(chunks: list[dict], n: int = 5) -> list[dict]:
    hits = []
    for c in chunks:
        meta = c.get("metadata") or {}
        if meta.get("agency") and meta.get("utterance_type") == "answer":
            hits.append(c)
    return hits[:n]


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_chunks()
    print(f"로드된 청크: {len(chunks):,}개\n")

    sep = "=" * 65

    # 1. Query → Agency extraction simulation
    print(sep)
    print("  쿼리 → 기관 추출 시뮬레이션")
    print(sep)
    for q in TEST_QUERIES:
        ag = extract_agency_from_query(q)
        q_preview = q[:45]
        print(f"  {q_preview:<45}  →  {ag or '(없음)'}")
    print()

    if not chunks:
        return

    # 2. Agency distribution
    print(sep)
    print("  청크 내 기관 분포 (agency != '')")
    print(sep)
    dist = agency_distribution(chunks)
    if dist:
        total_with_agency = sum(dist.values())
        for ag, cnt in list(dist.items())[:15]:
            bar = "█" * min(cnt, 40)
            print(f"  {ag:<20} {cnt:>6,}개  {bar}")
        print(f"\n  (총 {total_with_agency:,}개 청크에 기관 태그, {len(dist)}개 기관)")
    else:
        print("  (기관 태그가 있는 청크 없음)")
    print()

    # 3. Answer chunks by agency
    print(sep)
    print("  utterance_type='answer' 청크 기관별 분포")
    print(sep)
    ans_dist = answer_by_agency(chunks)
    if ans_dist:
        total_answers = sum(ans_dist.values())
        for ag, cnt in list(ans_dist.items())[:15]:
            bar = "█" * min(cnt, 40)
            print(f"  {ag:<20} {cnt:>6,}개  {bar}")
        print(f"\n  (총 {total_answers:,}개 answer 청크에 기관 태그)")
    else:
        print("  (answer 청크 없음)")
    print()

    # 4. 3-part structure preview
    print(sep)
    print("  3항 구조 미리보기 (질의자 → 기관 → 답변)")
    print(sep)
    top = top_agency_answers(chunks)
    if top:
        for i, c in enumerate(top, 1):
            meta = c.get("metadata") or {}
            prev_speaker = meta.get("prev_speaker", "(없음)")
            prev_role = meta.get("prev_speaker_role", "")
            agency = meta.get("agency", "")
            text_preview = c.get("clean_text", "")[:200]
            print(f"\n  [{i}] 질의자: {prev_speaker} ({prev_role})")
            print(f"       기관: {agency}")
            print(f"       답변: {text_preview}...")
    else:
        print("  (기관 태그가 있는 answer 청크 없음)")
    print()

    print(sep)


if __name__ == "__main__":
    main()
