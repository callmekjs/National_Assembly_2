# Algorithm #7: 회의 타임라인/국면 분절 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 회의 내 국면(개회→보고→질의응답→마무리)을 청크마다 태깅하고, `comparison`/`meeting_summary` 질문 유형에서 검색 결과를 회의일·발언 순서대로 정렬해 LLM이 시계열 맥락을 순서대로 읽게 한다.

**Architecture:** (1) `infer_meeting_phase(text, utterance_type)` — regex 기반 6-구분 분류기를 `question_types.py`에 추가. (2) chunker_v2.py에서 `metadata["meeting_phase"]` 저장. (3) `_apply_chronological_sort(hits, question_type)` — comparison/meeting_summary에 한해 (meeting_date, turn_index) 오름차순 정렬을 `retriever.py`에 추가 후 search()/search_v2() 끝단에 연결.

**Tech Stack:** Python stdlib (re), 기존 retriever.py + question_types.py + chunker_v2.py 구조

## Global Constraints

- 신규 패키지 의존성 추가 금지
- `infer_meeting_phase` 반환 타입: `str`, 가능한 값은 `"opening" | "presentation" | "qa" | "procedural" | "closing" | "unknown"` 6개만
- 3개 phase 패턴 상수(`_PHASE_OPENING`, `_PHASE_PRESENTATION`, `_PHASE_CLOSING`)는 `question_types.py`의 `_IMPORTANCE_FORMAL` 상수 직후(line ~154)에 추가
- `infer_meeting_phase` 함수는 `question_types.py`의 맨 마지막 함수로 추가
- chunker_v2.py: `meta["meeting_phase"]` 는 `meta["importance_score"]` 직후, `meta["question_type_hints"]` 직전에 저장
- `_apply_chronological_sort(hits, question_type)`: 대상 question_type = `{"comparison", "meeting_summary"}`만 정렬, 나머지는 no-op
- 정렬 키: `(metadata["meeting_date"], _parse_turn_index(chunk_id))` — 두 필드 모두 오름차순 (날짜 없으면 `""`, turn_index 없으면 `0`)
- `_apply_chronological_sort` 는 항상-on (별도 파라미터 없음)
- search()에서 호출 위치: smart merge 직후, `# Parent Document Retrieval` 직전
- search_v2()에서 호출 위치: smart merge 직후, `_enrich_with_context` 직전
- 기존 tests 190개 전부 통과 유지

---

### Task 1: `infer_meeting_phase` — 국면 분류 함수 추가

**Files:**
- Modify: `service/rag/query/question_types.py` (상수 3개 + 함수 1개)
- Test: `tests/test_question_types.py` (하단 추가, 9개 테스트)

**Interfaces:**
- Produces: `infer_meeting_phase(text: str, utterance_type: str = "") -> str`

- [ ] **Step 1: 테스트 먼저 작성**

`tests/test_question_types.py` 하단에 추가:

```python
from service.rag.query.question_types import infer_meeting_phase


def test_phase_opening():
    assert infer_meeting_phase("개의합니다. 오늘 회의를 시작하겠습니다.") == "opening"


def test_phase_opening_variant():
    assert infer_meeting_phase("위원회를 개의하겠습니다. 의사일정 상정합니다.") == "opening"


def test_phase_closing_산회():
    assert infer_meeting_phase("이상으로 회의를 마치겠습니다. 산회합니다.") == "closing"


def test_phase_closing_의결():
    assert infer_meeting_phase("가결되었습니다. 의결합니다.") == "closing"


def test_phase_presentation_with_answer():
    assert infer_meeting_phase("현안 보고 드리겠습니다. 다음과 같이 보고합니다.", utterance_type="answer") == "presentation"


def test_phase_presentation_text_but_question_type_is_qa():
    # presentation 텍스트라도 utterance_type=question이면 qa
    assert infer_meeting_phase("현안 보고 드리겠습니다.", utterance_type="question") == "qa"


def test_phase_qa_question():
    assert infer_meeting_phase("이 사안에 대해 어떻게 생각하십니까?", utterance_type="question") == "qa"


def test_phase_qa_answer():
    assert infer_meeting_phase("답변드리겠습니다. 검토하겠습니다.", utterance_type="answer") == "qa"


def test_phase_procedural():
    assert infer_meeting_phase("잠깐 정회하겠습니다.", utterance_type="procedural") == "procedural"


def test_phase_unknown_empty():
    assert infer_meeting_phase("") == "unknown"
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```
python -m pytest tests/test_question_types.py::test_phase_opening -v
```
Expected: `ImportError` 또는 `NameError`

- [ ] **Step 3: 상수 3개 추가**

`service/rag/query/question_types.py`에서 `_IMPORTANCE_FORMAL` 상수 직후(line ~154)에 아래 3개 상수를 삽입:

```python
_PHASE_OPENING = re.compile(
    r"개의합니다|회의를\s*시작|의사일정\s*상정|위원회를\s*개의|개의를\s*선언|개회합니다"
)

_PHASE_PRESENTATION = re.compile(
    r"현안\s*보고|업무\s*보고|결과\s*보고|보고\s*드리겠습니다|다음과\s*같이\s*보고|주요\s*현안"
)

_PHASE_CLOSING = re.compile(
    r"산회합니다|산회를\s*선언|이상으로\s*마치|회의를\s*마치|폐회합니다"
    r"|의결하겠습니다|가결되었습니다|부결되었습니다"
)
```

- [ ] **Step 4: `infer_meeting_phase` 함수 추가**

파일 맨 끝에 추가 (기존 `infer_importance_score` 함수 다음):

```python
def infer_meeting_phase(text: str, utterance_type: str = "") -> str:
    body = (text or "").strip()
    if not body:
        return "unknown"
    if _PHASE_OPENING.search(body):
        return "opening"
    if _PHASE_CLOSING.search(body):
        return "closing"
    if _PHASE_PRESENTATION.search(body) and utterance_type in ("answer", "statement", ""):
        if utterance_type != "question":
            return "presentation"
    if utterance_type in ("question", "answer"):
        return "qa"
    if utterance_type == "procedural":
        return "procedural"
    return "unknown"
```

참고: `_PHASE_PRESENTATION.search(body) and utterance_type != "question"` — presentation 텍스트라도 utterance_type="question"이면 qa로 분류한다. (의원이 "현안보고에 대해 질문드리겠습니다"처럼 쓰는 경우 대응)

- [ ] **Step 5: 테스트 실행 → 9개 PASS 확인**

```
python -m pytest tests/test_question_types.py -k "phase" -v
```
Expected: 9 tests PASS

- [ ] **Step 6: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 199 passed (기존 190 + 신규 9)

추가 imports 확인: 기존 import문에 `infer_meeting_phase` 이름이 없어도 됨 (test에서 직접 import).

- [ ] **Step 7: 커밋**

```
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "feat: infer_meeting_phase — 회의 국면 분류 함수 추가 (Algorithm #7)"
```

---

### Task 2: chunker_v2.py `meeting_phase` 메타데이터 저장

**Files:**
- Modify: `service/etl/transform/chunker_v2.py`
- Test: `tests/test_chunker_v2.py` (하단 추가, 4개 테스트)

**Interfaces:**
- Consumes: `infer_meeting_phase` (Task 1에서 추가됨)
- Produces: `metadata["meeting_phase"]` in each chunk record

- [ ] **Step 1: 테스트 먼저 작성**

`tests/test_chunker_v2.py` 하단에 추가:

```python
def test_meeting_phase_opening():
    turn = _turn("개의합니다. 회의를 시작하겠습니다.", "위원장", "위원장", 0)
    rec = _build_record(turn, "src001")
    assert rec["metadata"]["meeting_phase"] == "opening"


def test_meeting_phase_qa_answer():
    turn = _turn("답변드리겠습니다. 검토하겠습니다.", "홍길동 장관", "장관", 5)
    rec = _build_record(turn, "src001")
    assert rec["metadata"]["meeting_phase"] == "qa"


def test_meeting_phase_presentation():
    turn = _turn("현안 보고 드리겠습니다. 주요 현안을 설명합니다.", "홍길동 장관", "장관", 2)
    rec = _build_record(turn, "src001")
    assert rec["metadata"]["meeting_phase"] in ("presentation", "qa")  # answer 타입이면 presentation


def test_meeting_phase_unknown():
    turn = _turn("알겠습니다.", "김위원", "위원", 10)
    rec = _build_record(turn, "src001")
    assert rec["metadata"]["meeting_phase"] in ("qa", "unknown", "procedural", "statement")
    # 단: meeting_phase 키 자체는 반드시 존재해야 함
    assert "meeting_phase" in rec["metadata"]
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```
python -m pytest tests/test_chunker_v2.py::test_meeting_phase_opening -v
```
Expected: FAIL (`KeyError: 'meeting_phase'`)

- [ ] **Step 3: chunker_v2.py에 import 추가**

`service/etl/transform/chunker_v2.py` 상단 import block에 `infer_meeting_phase` 추가:

```python
from service.rag.query.question_types import (
    embed_hint_labels,
    infer_agency,
    infer_chunk_question_type_hints,
    infer_importance_score,
    infer_issue_score,
    infer_meeting_phase,
    infer_utterance_type_with_confidence,
)
```

- [ ] **Step 4: `_enrich_question_type_metadata` 수정**

`service/etl/transform/chunker_v2.py`의 `_enrich_question_type_metadata` 함수에서, `meta["importance_score"]` 저장 직후, `meta["question_type_hints"]` 저장 직전에 한 줄 삽입:

현재 코드 (~line 109-119):
```python
    meta["importance_score"] = infer_importance_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["question_type_hints"] = infer_chunk_question_type_hints(
```

변경 후:
```python
    meta["importance_score"] = infer_importance_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["meeting_phase"] = infer_meeting_phase(text, utype)
    meta["question_type_hints"] = infer_chunk_question_type_hints(
```

- [ ] **Step 5: 테스트 실행 → 4개 PASS 확인**

```
python -m pytest tests/test_chunker_v2.py -k "meeting_phase" -v
```
Expected: 4 tests PASS

- [ ] **Step 6: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 203 passed (기존 199 + 신규 4)

- [ ] **Step 7: 커밋**

```
git add service/etl/transform/chunker_v2.py tests/test_chunker_v2.py
git commit -m "feat: meeting_phase metadata 저장 — chunker_v2 국면 태깅 (Algorithm #7)"
```

---

### Task 3: `_apply_chronological_sort` 구현 + retriever wiring

**Files:**
- Modify: `service/rag/retrieval/retriever.py`
- Test: `tests/test_retriever_v2.py` (하단 추가, 6개 테스트)

**Interfaces:**
- Consumes: `_parse_turn_index` (Algorithm #6 Task 1에서 추가됨, 같은 파일)
- Produces: `_apply_chronological_sort(hits: list[dict], question_type: str | None) -> list[dict]`

**삽입 위치:** `_merge_adjacent_hits` 함수 직후, `_rrf_merge` 함수 직전

- [ ] **Step 1: 테스트 먼저 작성**

`tests/test_retriever_v2.py` 하단에 추가:

```python
from service.rag.retrieval.retriever import _apply_chronological_sort


def _dated_hit(date: str, turn: int, score: float = 0.5) -> dict:
    return {
        "chunk_id": f"src_{date.replace('-', '')}_turn_{turn:04d}",
        "source_id": f"src_{date.replace('-', '')}",
        "content": f"발언 {date} turn={turn}",
        "hybrid_score": score,
        "metadata": {"meeting_date": date},
    }


def test_chronological_sort_comparison_orders_by_date():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="comparison")
    assert result[0]["metadata"]["meeting_date"] == "2024-03-01"
    assert result[1]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_meeting_summary_orders_by_date_then_turn():
    hits = [
        _dated_hit("2024-03-01", 5, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="meeting_summary")
    assert result[0]["chunk_id"].endswith("_turn_0002")
    assert result[1]["chunk_id"].endswith("_turn_0005")


def test_chronological_sort_noop_for_topic_search():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type="topic_search")
    # 순서 그대로 유지 (2024-06 first)
    assert result[0]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_noop_for_none_question_type():
    hits = [
        _dated_hit("2024-06-01", 1, score=0.9),
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    result = _apply_chronological_sort(hits, question_type=None)
    assert result[0]["metadata"]["meeting_date"] == "2024-06-01"


def test_chronological_sort_handles_missing_date():
    hits = [
        {"chunk_id": "src_turn_0001", "source_id": "src", "content": "A", "hybrid_score": 0.9, "metadata": {}},
        _dated_hit("2024-03-01", 2, score=0.5),
    ]
    # date 없는 항목은 "" → 앞으로 정렬됨 (빈 문자열이 날짜보다 앞)
    result = _apply_chronological_sort(hits, question_type="comparison")
    assert len(result) == 2  # 개수 변화 없음


def test_chronological_sort_empty_hits():
    result = _apply_chronological_sort([], question_type="comparison")
    assert result == []
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```
python -m pytest tests/test_retriever_v2.py::test_chronological_sort_comparison_orders_by_date -v
```
Expected: `ImportError` (`_apply_chronological_sort` 미존재)

- [ ] **Step 3: `_apply_chronological_sort` 함수 추가**

`service/rag/retrieval/retriever.py`에서 `_merge_adjacent_hits` 함수 직후, `_rrf_merge` 함수 직전에 삽입:

```python
def _apply_chronological_sort(
    hits: list[dict], question_type: str | None
) -> list[dict]:
    """comparison/meeting_summary 질문 유형에서 (회의일, turn_index) 오름차순으로 재정렬."""
    if (question_type or "").strip() not in {"comparison", "meeting_summary"}:
        return hits
    def _key(h: dict) -> tuple[str, int]:
        date = (h.get("metadata") or {}).get("meeting_date") or ""
        tidx = _parse_turn_index(str(h.get("chunk_id") or "")) or 0
        return (date, tidx)
    return sorted(hits, key=_key)
```

- [ ] **Step 4: search() wiring**

`service/rag/retrieval/retriever.py`의 `search()` 메서드에서 smart merge 블록 직후에 삽입:

```python
        # Smart Chunk Merge — 인접 발언 병합
        if use_smart_merge and out:
            out = _merge_adjacent_hits(out)

        # Chronological Sort — comparison/meeting_summary 시계열 정렬
        out = _apply_chronological_sort(out, question_type=question_type)

        # Parent Document Retrieval — 검색 후 문맥 확장
```

- [ ] **Step 5: search_v2() wiring**

`service/rag/retrieval/retriever.py`의 `search_v2()` 메서드에서 smart merge 직후에 수정:

```python
        # Smart Chunk Merge — 인접 발언 병합
        if use_smart_merge and merged:
            merged = _merge_adjacent_hits(merged)
        # Chronological Sort — comparison/meeting_summary 시계열 정렬
        merged = _apply_chronological_sort(merged, question_type=question_type)
        return self._enrich_with_context(merged)
```

- [ ] **Step 6: 테스트 실행 → 6개 PASS 확인**

```
python -m pytest tests/test_retriever_v2.py -k "chronological" -v
```
Expected: 6 tests PASS

- [ ] **Step 7: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 209 passed (기존 203 + 신규 6)

- [ ] **Step 8: 커밋**

```
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: _apply_chronological_sort — comparison/summary 시계열 정렬 (Algorithm #7)"
```

---

### Task 4: `eval/meeting_timeline_eval.py` 평가 스크립트

**Files:**
- Create: `eval/meeting_timeline_eval.py`

**Interfaces:**
- Consumes: `infer_meeting_phase` (Task 1), `_apply_chronological_sort`, `_parse_turn_index` (retriever), 청크 파일 `data/v2/transform/final/chunks_v2.jsonl`

- [ ] **Step 1: 스크립트 작성**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"
MAX_LOAD = 3000
sep = "=" * 65

_PHASE_ORDER = ["opening", "presentation", "qa", "procedural", "closing", "unknown"]


def load_chunks(n: int = MAX_LOAD) -> list[dict]:
    if not CHUNKS_FILE.exists():
        print(f"[meeting_timeline_eval] chunks file not found: {CHUNKS_FILE}")
        return []
    chunks = []
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
            if len(chunks) >= n:
                break
    return chunks


def phase_distribution(chunks: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {p: 0 for p in _PHASE_ORDER}
    for c in chunks:
        phase = (c.get("metadata") or {}).get("meeting_phase", "unknown") or "unknown"
        dist[phase] = dist.get(phase, 0) + 1
    return dist


def chronological_sort_demo(chunks: list[dict]) -> None:
    from service.rag.retrieval.retriever import _apply_chronological_sort, _parse_turn_index

    # 다른 회의일의 청크 샘플링 (최대 6개, 최소 2개 날짜)
    by_date: dict[str, list[dict]] = {}
    for c in chunks:
        date = (c.get("metadata") or {}).get("meeting_date", "") or ""
        if date:
            by_date.setdefault(date, []).append(c)

    if len(by_date) < 2:
        print("  (다른 날짜의 청크 없음 — 시연 불가)")
        return

    # 날짜 2개 선택, 각 3개씩
    dates = sorted(by_date.keys(), reverse=True)[:2]
    sample: list[dict] = []
    for d in dates:
        sample.extend(by_date[d][:3])

    # 점수 역순으로 섞기 (정렬 전처럼 랜덤한 순서)
    import random
    random.shuffle(sample)
    for i, c in enumerate(sample):
        c["hybrid_score"] = round(0.9 - i * 0.1, 2)

    # comparison 질문 유형으로 시계열 정렬
    def _to_hit(c: dict) -> dict:
        return {
            "chunk_id": c.get("chunk_id", ""),
            "source_id": c.get("source_id", ""),
            "content": c.get("clean_text") or c.get("content") or "",
            "hybrid_score": c.get("hybrid_score", 0.5),
            "metadata": c.get("metadata", {}),
        }

    hits = [_to_hit(c) for c in sample]
    sorted_hits = _apply_chronological_sort(hits, question_type="comparison")

    print("정렬 전 (hybrid_score 순):")
    for h in hits[:4]:
        date = (h.get("metadata") or {}).get("meeting_date", "날짜없음")
        tidx = _parse_turn_index(str(h.get("chunk_id") or "")) or 0
        print(f"  [{date}] turn={tidx:4d}  score={h['hybrid_score']:.2f}  {h['content'][:60]}...")

    print()
    print("정렬 후 (시계열 오름차순):")
    for h in sorted_hits[:4]:
        date = (h.get("metadata") or {}).get("meeting_date", "날짜없음")
        tidx = _parse_turn_index(str(h.get("chunk_id") or "")) or 0
        print(f"  [{date}] turn={tidx:4d}  score={h['hybrid_score']:.2f}  {h['content'][:60]}...")


def main() -> None:
    chunks = load_chunks()
    print(f"[meeting_timeline_eval] loaded {len(chunks)} chunks")
    print()

    print(sep)
    print("=== 회의 국면(meeting_phase) 분포 ===")
    dist = phase_distribution(chunks)
    total = sum(dist.values())
    for phase in _PHASE_ORDER:
        cnt = dist.get(phase, 0)
        pct = cnt / max(total, 1)
        bar = "#" * min(int(pct * 40), 40)
        print(f"  {phase:<15}  {cnt:5d}  ({pct:.1%})  {bar}")
    print(f"  (총 {total}개 청크)")
    print()

    print(sep)
    print("=== 시계열 정렬 시뮬레이션 (comparison 질문 유형) ===")
    chronological_sort_demo(chunks)
    print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 검증**

```
python -c "import ast; ast.parse(open('eval/meeting_timeline_eval.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 209 passed

- [ ] **Step 4: 커밋**

```
git add eval/meeting_timeline_eval.py
git commit -m "eval: meeting_timeline_eval 스크립트 추가 (Algorithm #7)"
```

---

## Self-Review

### 1. Spec Coverage

| 요구사항 | 태스크 |
|---|---|
| `infer_meeting_phase` 함수 | Task 1 |
| 6개 반환값 (`opening`, `presentation`, `qa`, `procedural`, `closing`, `unknown`) | Task 1 |
| `_PHASE_OPENING`, `_PHASE_PRESENTATION`, `_PHASE_CLOSING` 상수 | Task 1 |
| chunker `metadata["meeting_phase"]` 저장 | Task 2 |
| `_apply_chronological_sort` 함수 | Task 3 |
| comparison/meeting_summary 에서만 정렬 | Task 3 |
| 정렬 키 `(meeting_date, turn_index)` | Task 3 |
| search() wiring (smart merge 직후) | Task 3 |
| search_v2() wiring (enrich_with_context 직전) | Task 3 |
| eval 스크립트 | Task 4 |

### 2. Placeholder 스캔

없음.

### 3. Type Consistency

- `infer_meeting_phase(text: str, utterance_type: str = "") -> str` — Task 1에서 정의, Task 2 chunker에서 호출, Task 4 eval에서 간접 사용
- `_apply_chronological_sort(hits: list[dict], question_type: str | None) -> list[dict]` — Task 3에서 정의, search()/search_v2() 양쪽 wiring
- `_parse_turn_index` — Algorithm #6 Task 1에서 이미 존재, Task 3에서 재사용 (새로 정의 X)

✅ 일관성 확인 완료.
