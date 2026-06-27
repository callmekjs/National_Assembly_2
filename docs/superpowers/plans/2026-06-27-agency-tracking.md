# Algorithm #5: 기관 답변 추적 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "외교부가 뭐라 했나?" 형태의 쿼리에서 기관명을 자동 추출하고, 해당 기관의 답변 청크만 필터링하며, 질의자-기관-답변 3항 구조를 결과에 포함해 LLM에 전달한다.

**Architecture:** `question_types.py`에 `extract_agency_from_query()`를 추가해 쿼리에서 기관명을 추출한다. `chunker_v2.py`의 `_add_context_window()`를 확장해 인접 발언자(`prev_speaker`)를 메타데이터에 저장한다. `retriever.py`에 `_resolve_agency_filter()`를 추가해 `agency_answer_tracking` 질문 유형 시 기관명을 자동 주입하고 `utterance_type="answer"` 필터를 강제한다. 기존 `agency` DB 필터와 `prev_speaker` 메타데이터가 결합되어 3항 구조(질의자-기관-답변)가 자동으로 완성된다.

**Tech Stack:** Python 3.11, re (stdlib), pytest, JSONL files

## Global Constraints

- 모든 변경은 `main` 브랜치에서 직접 진행 (워크트리 없음)
- `extract_agency_from_query(query: str) -> str | None` — `_AGENCY_ALIASES`를 순서대로 스캔, 첫 매칭 반환 (없으면 None)
- `_AGENCY_ALIASES`: 기존 12개 항목을 유지하고 10개 추가 (총 22개 이상)
- `metadata["prev_speaker"]`: answer 타입 청크에 이전 발언자 이름 저장
- `metadata["prev_speaker_role"]`: answer 타입 청크에 이전 발언자 역할 저장
- `_resolve_agency_filter(query, question_type, agency, utterance_type) -> tuple[str, str]` — 모듈 수준 함수, 이름 고정
- `agency_answer_tracking` 시: `agency` 자동 추출, `utterance_type` 강제 `"answer"` (이미 값 있으면 유지)
- 기존 테스트 전체 통과 유지 (`pytest tests/ -q`)
- 새 테스트는 기존 파일에 추가 (새 파일 생성 금지): `tests/test_question_types.py`, `tests/test_chunker_v2.py`, `tests/test_retriever_v2.py`
- 코드 주석 금지 (WHY가 자명한 경우)

---

## 파일 구조

| 역할 | 파일 | 작업 |
|---|---|---|
| 기관 추출 함수 + 확장 alias | `service/rag/query/question_types.py` | 수정 (Task 1) |
| 인접 발언자 메타데이터 | `service/etl/transform/chunker_v2.py` | 수정 (Task 2) |
| 기관 필터 자동 주입 | `service/rag/retrieval/retriever.py` | 수정 (Task 3) |
| 기관 추출 테스트 | `tests/test_question_types.py` | 수정 (Task 1) |
| 청커 테스트 | `tests/test_chunker_v2.py` | 수정 (Task 2) |
| 리트리버 테스트 | `tests/test_retriever_v2.py` | 수정 (Task 3) |
| Before/After 평가 | `eval/agency_tracking_eval.py` | 신규 (Task 4) |

---

### Task 1: `extract_agency_from_query()` + `_AGENCY_ALIASES` 확장

**Files:**
- Modify: `service/rag/query/question_types.py`
- Modify: `tests/test_question_types.py`

**Interfaces:**
- Consumes: 기존 `_AGENCY_ALIASES` (line ~192)
- Produces: `extract_agency_from_query(query: str) -> str | None`

**현재 `_AGENCY_ALIASES` (line 192–205):**
```python
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
```

이 tuple을 다음으로 교체한다 (기존 12개 유지 + 10개 추가 = 22개):

```python
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
    ("과학기술정보통신부", "과학기술정보통신부"),
    ("방송통신위원회", "방송통신위원회"),
    ("금융위원회", "금융위원회"),
    ("공정거래위원회", "공정거래위원회"),
    ("국토교통부", "국토교통부"),
    ("보건복지부", "보건복지부"),
    ("환경부", "환경부"),
    ("고용노동부", "고용노동부"),
    ("산업통상자원부", "산업통상자원부"),
    ("교육부", "교육부"),
)
```

그리고 `infer_agency` 함수 아래에 `extract_agency_from_query`를 추가한다:

```python
def extract_agency_from_query(query: str) -> str | None:
    blob = (query or "").strip()
    if not blob:
        return None
    for token, agency in _AGENCY_ALIASES:
        if token in blob:
            return agency
    return None
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_question_types.py` import 줄에 `extract_agency_from_query` 추가:
```python
from service.rag.query.question_types import classify_question, route_defaults, infer_utterance_type, infer_utterance_type_with_confidence, infer_issue_score, infer_importance_score, extract_agency_from_query
```

파일 맨 아래에 다음 6개 테스트 추가:

```python
def test_extract_agency_known_agency():
    assert extract_agency_from_query("외교부가 재외국민 보호에 대해 뭐라 했나?") == "외교부"


def test_extract_agency_alias_mapping():
    assert extract_agency_from_query("국정원의 입장은?") == "국가정보원"


def test_extract_agency_new_agency():
    assert extract_agency_from_query("금융위원회의 답변을 알고 싶다") == "금융위원회"


def test_extract_agency_returns_none_for_no_match():
    assert extract_agency_from_query("일반적인 정책 질의") is None


def test_extract_agency_returns_none_for_empty():
    assert extract_agency_from_query("") is None


def test_extract_agency_first_match_wins():
    result = extract_agency_from_query("외교부와 통일부의 협력 방안")
    assert result == "외교부"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_question_types.py::test_extract_agency_known_agency -v
```

Expected: FAIL (`extract_agency_from_query` 미존재)

- [ ] **Step 3: `_AGENCY_ALIASES` 교체 + `extract_agency_from_query` 추가**

위 설명에 따라 `_AGENCY_ALIASES`를 22개로 교체하고, `infer_agency` 직후에 `extract_agency_from_query` 추가.

최종 배치:
```python
def infer_agency(speaker_role: str, text: str = "") -> str:
    blob = f"{speaker_role or ''} {text or ''}"
    for token, agency in _AGENCY_ALIASES:
        if token in blob:
            return agency
    return ""


def extract_agency_from_query(query: str) -> str | None:
    blob = (query or "").strip()
    if not blob:
        return None
    for token, agency in _AGENCY_ALIASES:
        if token in blob:
            return agency
    return None
```

- [ ] **Step 4: 테스트 실행**

```bash
python -m pytest tests/test_question_types.py -v
```

Expected: 40개 통과 (기존 34개 + 새 6개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "feat: extract_agency_from_query + _AGENCY_ALIASES 확장 (Algorithm #5)"
```

---

### Task 2: 청커 `prev_speaker` / `prev_speaker_role` 메타데이터

**Files:**
- Modify: `service/etl/transform/chunker_v2.py`
- Modify: `tests/test_chunker_v2.py`

**Interfaces:**
- Consumes: 없음 (독립 Task)
- Produces: `metadata["prev_speaker"]: str`, `metadata["prev_speaker_role"]: str` — 이전 발언자 정보

**현재 `_add_context_window` (line 232–239):**
```python
def _add_context_window(records: list[dict]) -> list[dict]:
    """각 청크 metadata에 인접 발언 앞 100자를 prev_context / next_context로 추가."""
    for i, rec in enumerate(records):
        if i > 0:
            rec["metadata"]["prev_context"] = records[i - 1]["clean_text"][:CONTEXT_CHARS]
        if i < len(records) - 1:
            rec["metadata"]["next_context"] = records[i + 1]["clean_text"][:CONTEXT_CHARS]
    return records
```

다음으로 교체한다:

```python
def _add_context_window(records: list[dict]) -> list[dict]:
    """각 청크 metadata에 인접 발언 앞 100자를 prev_context / next_context로 추가."""
    for i, rec in enumerate(records):
        if i > 0:
            prev = records[i - 1]
            rec["metadata"]["prev_context"] = prev["clean_text"][:CONTEXT_CHARS]
            rec["metadata"]["prev_speaker"] = prev.get("speaker", "")
            rec["metadata"]["prev_speaker_role"] = prev.get("speaker_role", "")
        if i < len(records) - 1:
            rec["metadata"]["next_context"] = records[i + 1]["clean_text"][:CONTEXT_CHARS]
    return records
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_chunker_v2.py`에 다음을 추가한다:

```python
def test_add_context_window_stores_prev_speaker():
    from service.etl.transform.chunker_v2 import _add_context_window
    records = [
        {"clean_text": "질의입니다.", "speaker": "홍기원", "speaker_role": "위원", "metadata": {}},
        {"clean_text": "답변드리겠습니다.", "speaker": "조태열", "speaker_role": "장관", "metadata": {}},
    ]
    result = _add_context_window(records)
    assert result[1]["metadata"]["prev_speaker"] == "홍기원"
    assert result[1]["metadata"]["prev_speaker_role"] == "위원"


def test_add_context_window_first_record_has_no_prev_speaker():
    from service.etl.transform.chunker_v2 import _add_context_window
    records = [
        {"clean_text": "첫 번째 발언.", "speaker": "홍기원", "speaker_role": "위원", "metadata": {}},
    ]
    result = _add_context_window(records)
    assert "prev_speaker" not in result[0]["metadata"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_chunker_v2.py::test_add_context_window_stores_prev_speaker -v
```

Expected: FAIL

- [ ] **Step 3: `_add_context_window` 수정**

위 설명대로 교체.

- [ ] **Step 4: 테스트 실행**

```bash
python -m pytest tests/test_chunker_v2.py -v
```

Expected: 20개 통과 (기존 18개 + 새 2개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/etl/transform/chunker_v2.py tests/test_chunker_v2.py
git commit -m "feat: _add_context_window에 prev_speaker/role 추가 (Algorithm #5)"
```

---

### Task 3: 리트리버 `_resolve_agency_filter()` + 자동 주입

**Files:**
- Modify: `service/rag/retrieval/retriever.py`
- Modify: `tests/test_retriever_v2.py`

**Interfaces:**
- Consumes: Task 1의 `extract_agency_from_query(query: str) -> str | None`
- Produces: `_resolve_agency_filter(query, question_type, agency, utterance_type) -> tuple[str, str]`

**`_resolve_agency_filter` 로직:**
- `question_type != "agency_answer_tracking"` 이면 `(agency or "", utterance_type or "")` 반환 (no-op)
- 해당하면:
  - `agency`: 이미 값 있으면 유지, 없으면 `extract_agency_from_query(query) or ""`
  - `utterance_type`: 이미 값 있으면 유지, 없으면 `"answer"` 강제
  - `(resolved_agency, resolved_utype)` 반환

**추가 위치 — `_apply_importance_boost` 함수 직후 (line ~37):**

```python
def _resolve_agency_filter(
    query: str,
    question_type: str | None,
    agency: str | None,
    utterance_type: str | None,
) -> tuple[str, str]:
    if (question_type or "").strip() != "agency_answer_tracking":
        return agency or "", utterance_type or ""
    from service.rag.query.question_types import extract_agency_from_query
    resolved_agency = agency or extract_agency_from_query(query) or ""
    resolved_utype = utterance_type or "answer"
    return resolved_agency, resolved_utype
```

**search() 수정 — `filters = {...}` 직전 (line ~145) 에 2줄 추가:**

현재:
```python
        df, dt = normalize_meeting_date_range(date_from, date_to)
        filters = {
            "committee": committee or "",
            ...
            "utterance_type": utterance_type or "",
            ...
            "agency": agency or "",
            ...
        }
```

다음으로 교체:
```python
        df, dt = normalize_meeting_date_range(date_from, date_to)
        agency_f, utype_f = _resolve_agency_filter(query, question_type, agency, utterance_type)
        filters = {
            "committee": committee or "",
            "date_from": df or "",
            "date_to": dt or "",
            "speaker": speaker or "",
            "require_speaker": require_speaker,
            "question_type": question_type or "",
            "utterance_type": utype_f,
            "party": party or "",
            "position_type": position_type or "",
            "agency": agency_f,
            "chunk_type": "qa_pair" if (question_type or "").strip() == "qa_pair_extract" else "utterance",
        }
```

**search_v2() 수정 — `filters = {...}` 직전 (line ~419) 에 동일하게 적용:**

현재:
```python
        df, dt = normalize_meeting_date_range(date_from, date_to)
        filters = {
            "committee": committee or "",
            ...
            "utterance_type": utterance_type or "",
            ...
            "agency": agency or "",
            ...
        }
```

다음으로 교체:
```python
        df, dt = normalize_meeting_date_range(date_from, date_to)
        agency_f, utype_f = _resolve_agency_filter(query, question_type, agency, utterance_type)
        filters = {
            "committee": committee or "",
            "date_from": df or "",
            "date_to": dt or "",
            "speaker": speaker or "",
            "require_speaker": require_speaker,
            "question_type": question_type or "",
            "utterance_type": utype_f,
            "party": party or "",
            "position_type": position_type or "",
            "agency": agency_f,
            "chunk_type": "qa_pair" if (question_type or "").strip() == "qa_pair_extract" else "utterance",
        }
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_retriever_v2.py` 맨 아래에 추가:

```python
from service.rag.retrieval.retriever import _resolve_agency_filter


def test_resolve_agency_filter_extracts_agency_and_forces_answer():
    agency, utype = _resolve_agency_filter(
        "외교부가 재외국민 보호에 대해 뭐라 했나?", "agency_answer_tracking", None, None
    )
    assert agency == "외교부"
    assert utype == "answer"


def test_resolve_agency_filter_noop_for_topic_search():
    agency, utype = _resolve_agency_filter("외교부 정책", "topic_search", None, None)
    assert agency == ""
    assert utype == ""


def test_resolve_agency_filter_preserves_explicit_agency():
    agency, utype = _resolve_agency_filter("질의", "agency_answer_tracking", "통일부", None)
    assert agency == "통일부"
    assert utype == "answer"


def test_resolve_agency_filter_no_match_returns_empty_agency():
    agency, utype = _resolve_agency_filter("일반 정책 질의", "agency_answer_tracking", None, None)
    assert agency == ""
    assert utype == "answer"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_retriever_v2.py::test_resolve_agency_filter_extracts_agency_and_forces_answer -v
```

Expected: FAIL (`_resolve_agency_filter` 미존재)

- [ ] **Step 3: retriever.py 수정**

`_apply_importance_boost` 함수 직후에 `_resolve_agency_filter` 추가. `search()` / `search_v2()` 양쪽의 `filters` 딕셔너리 직전에 `agency_f, utype_f = _resolve_agency_filter(...)` 호출 추가.

- [ ] **Step 4: 전체 테스트 실행**

```bash
python -m pytest tests/test_retriever_v2.py -v
```

Expected: 16개 통과 (기존 12개 + 새 4개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: agency_answer_tracking 기관 자동 추출 + answer 필터 주입 (Algorithm #5)"
```

---

### Task 4: Before/After 평가 스크립트

**Files:**
- Create: `eval/agency_tracking_eval.py`

**Interfaces:**
- Consumes:
  - `data/v2/transform/final/chunks_v2.jsonl`
  - Task 1–3의 `extract_agency_from_query`, `_resolve_agency_filter`
- Produces: stdout 리포트

**평가 내용:**
1. 기관별 answer 청크 분포 (agency 필드가 있는 utterance_type="answer" 청크)
2. prev_speaker 커버리지 (answer 청크 중 prev_speaker 있는 비율)
3. 3항 구조 샘플 10건: `prev_speaker → agency → clean_text[:80]`
4. 쿼리 추출 시뮬레이션: 테스트 쿼리 5개에 대해 추출 결과 출력

- [ ] **Step 1: 스크립트 작성**

`eval/agency_tracking_eval.py`를 아래 내용으로 작성한다:

```python
"""
기관 답변 추적 알고리즘 Before/After 평가

사용법:
    python eval/agency_tracking_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import extract_agency_from_query
from service.rag.retrieval.retriever import _resolve_agency_filter


def load_chunks() -> list[dict]:
    chunks = []
    if not CHUNKS_FILE.exists():
        print(f"청크 파일 없음: {CHUNKS_FILE}")
        return chunks
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            if c.get("metadata", {}).get("chunk_type", "utterance") == "utterance":
                chunks.append(c)
    return chunks


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_chunks()
    if not chunks:
        return
    print(f"utterance 청크: {len(chunks):,}개\n")

    sep = "=" * 65

    # 기관별 answer 청크 분포
    answer_chunks = [c for c in chunks if c.get("metadata", {}).get("utterance_type") == "answer"]
    agency_counter: Counter = Counter()
    for c in answer_chunks:
        ag = c.get("metadata", {}).get("agency", "") or "(없음)"
        agency_counter[ag] += 1

    print(sep)
    print("  기관별 answer 청크 분포 (상위 15개)")
    print(sep)
    for agency, count in agency_counter.most_common(15):
        pct = count / max(len(answer_chunks), 1) * 100
        bar = "█" * min(20, int(pct / 2))
        print(f"  {agency:<18} {count:>6,}개 ({pct:4.1f}%) {bar}")

    # prev_speaker 커버리지
    answer_with_agency = [c for c in answer_chunks if c.get("metadata", {}).get("agency")]
    prev_speaker_set = [c for c in answer_with_agency if c.get("metadata", {}).get("prev_speaker")]
    coverage = len(prev_speaker_set) / max(len(answer_with_agency), 1) * 100

    print(f"\n{sep}")
    print("  3항 구조 커버리지")
    print(sep)
    print(f"  agency 있는 answer 청크: {len(answer_with_agency):,}개")
    print(f"  prev_speaker 있는 비율:  {len(prev_speaker_set):,}개 ({coverage:.1f}%)")

    # 3항 구조 샘플
    print(f"\n{sep}")
    print("  3항 구조 샘플 10건: [질의자] → [기관] → [답변 앞 80자]")
    print(sep)
    samples = [c for c in prev_speaker_set if c.get("metadata", {}).get("agency")][:10]
    for c in samples:
        meta = c.get("metadata", {})
        questioner = meta.get("prev_speaker", "?")
        agency = meta.get("agency", "?")
        text = c.get("clean_text", "")[:80]
        print(f"  [{questioner}] → [{agency}] → {text}...")

    # 쿼리 추출 시뮬레이션
    print(f"\n{sep}")
    print("  쿼리 기관 추출 시뮬레이션")
    print(sep)
    test_queries = [
        "외교부가 재외국민 보호에 대해 뭐라 했나?",
        "국정원의 정보 공유 관련 답변을 알고 싶다",
        "금융위원회의 답변 내용은?",
        "교육부 장관이 어떻게 답변했나요",
        "일반적인 정책 현황 질의",
    ]
    for q in test_queries:
        agency_f, utype_f = _resolve_agency_filter(q, "agency_answer_tracking", None, None)
        matched = [c for c in answer_chunks if c.get("metadata", {}).get("agency") == agency_f] if agency_f else []
        print(f"  쿼리: {q[:40]}")
        print(f"    추출 기관: {agency_f or '(없음)'}  utterance_type: {utype_f}  매칭 청크: {len(matched):,}개")

    print(sep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행**

```bash
python eval/agency_tracking_eval.py
```

Expected: 리포트 정상 출력 또는 "청크 파일 없음" 메시지

- [ ] **Step 3: 커밋**

```bash
git add eval/agency_tracking_eval.py
git commit -m "eval: 기관 답변 추적 before/after 평가 스크립트 추가"
```

---

## Self-Review

**Spec coverage:**
- ✅ `extract_agency_from_query(query) -> str | None` — `_AGENCY_ALIASES` 순서 스캔, 없으면 None (Task 1)
- ✅ `_AGENCY_ALIASES` 22개 (기존 12개 + 10개 신규) (Task 1)
- ✅ `metadata["prev_speaker"]`, `metadata["prev_speaker_role"]` — `_add_context_window` 확장 (Task 2)
- ✅ `_resolve_agency_filter(query, question_type, agency, utterance_type) -> tuple[str, str]` (Task 3)
- ✅ `agency_answer_tracking` 시 agency 자동 추출 + utterance_type="answer" 강제 (Task 3)
- ✅ search() + search_v2() 양쪽 통합 (Task 3)
- ✅ eval: 3항 구조 커버리지 + 샘플 + 쿼리 시뮬레이션 (Task 4)

**Placeholder scan:** 없음

**Type consistency:**
- `extract_agency_from_query` → `str | None` — Task 1 정의, Task 3 `_resolve_agency_filter` 내부 소비 일치
- `_resolve_agency_filter` → `tuple[str, str]` — Task 3 정의, 테스트에서 직접 import 일치
- `metadata["prev_speaker"]` 키 — Task 2 저장, Task 4 eval에서 읽기 일치

**Logic verification (test_resolve_agency_filter_extracts_agency_and_forces_answer):**
- query: "외교부가 재외국민 보호에 대해 뭐라 했나?"
- question_type: "agency_answer_tracking"
- `extract_agency_from_query("외교부가...")` → "외교부" (_AGENCY_ALIASES 첫 번째 항목)
- resolved_agency = "외교부", resolved_utype = "answer" ✓

**Logic verification (test_resolve_agency_filter_preserves_explicit_agency):**
- agency 파라미터 = "통일부" (이미 있음) → resolved_agency = "통일부" (유지)
- utterance_type 파라미터 = None → resolved_utype = "answer" (강제) ✓
