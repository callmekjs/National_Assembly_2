# Algorithm #6: 스마트 청크 병합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 검색 결과에서 같은 회의의 인접 발언(turn_index 차 ≤ 2)을 자동으로 하나의 컨텍스트 블록으로 병합해 LLM에게 대화 단위 맥락을 제공한다.

**Architecture:** 순수 후처리 함수 `_merge_adjacent_hits(hits, gap=2)`를 `retriever.py`에 추가한다. chunk_id에서 turn_index를 파싱해 같은 source_id의 인접 청크를 time-order로 합치고, 합산 길이가 `_MERGE_MAX_CHARS=1200`을 초과하면 병합하지 않는다. `search()`와 `search_v2()` 양쪽에 `use_smart_merge: bool = True` 파라미터로 게이트한다.

**Tech Stack:** Python stdlib (re), 기존 retriever.py 구조

## Global Constraints

- 신규 패키지 의존성 추가 금지
- chunk_id 형식: `{source_id}_turn_{turn_index:04d}` (chunker_v2.py 기준) — qa_pair는 `_qa_` 포함이므로 자동으로 미병합
- `_ADJACENT_GAP = 2`, `_MERGE_MAX_CHARS = 1200` 모듈 상수로 선언
- 병합된 청크의 content: 두 청크를 turn_index 오름차순(시간순)으로 `"\n\n"` 구분자로 결합
- 병합된 청크의 hybrid_score: 두 청크 중 max 값
- 병합된 청크에 `_merged_chunk_ids: list[str]` 필드 추가
- 기존 tests 179개 전부 통과 유지
- `search()` 기준: use_smart_merge 적용 위치 = top_k 슬라이싱 **직후**, `use_parent_doc` 블록 **직전**
- `search_v2()` 기준: `_enrich_with_context()` 호출 **직전**

---

### Task 1: `_parse_turn_index` + `_merge_adjacent_hits` 구현 + 테스트

**Files:**
- Modify: `service/rag/retrieval/retriever.py` (모듈 상수 + 두 함수를 `_resolve_agency_filter` 직후에 추가)
- Test: `tests/test_retriever_v2.py` (기존 파일 하단에 추가, 8개 테스트)

**Interfaces:**
- Produces:
  - `_ADJACENT_GAP: int = 2`
  - `_MERGE_MAX_CHARS: int = 1200`
  - `_parse_turn_index(chunk_id: str) -> int | None`
  - `_merge_adjacent_hits(hits: list[dict], gap: int = _ADJACENT_GAP) -> list[dict]`

- [ ] **Step 1: 테스트 먼저 작성**

`tests/test_retriever_v2.py` 하단에 추가:

```python
from service.rag.retrieval.retriever import (
    _parse_turn_index,
    _merge_adjacent_hits,
    _ADJACENT_GAP,
    _MERGE_MAX_CHARS,
)


def _hit(source_id: str, turn: int, content: str = "내용", score: float = 0.5) -> dict:
    return {
        "chunk_id": f"{source_id}_turn_{turn:04d}",
        "source_id": source_id,
        "content": content,
        "hybrid_score": score,
    }


def test_parse_turn_index_standard():
    assert _parse_turn_index("20240717_52128_52128_turn_0003") == 3


def test_parse_turn_index_none_for_qa():
    assert _parse_turn_index("20240717_52128_52128_qa_0001") is None


def test_parse_turn_index_none_for_empty():
    assert _parse_turn_index("") is None


def test_merge_adjacent_two_hits():
    hits = [_hit("src", 1, "A내용", 0.9), _hit("src", 2, "B내용", 0.7)]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 1
    assert "A내용" in result[0]["content"]
    assert "B내용" in result[0]["content"]
    assert result[0]["hybrid_score"] == 0.9
    assert result[0]["_merged_chunk_ids"] == ["src_turn_0001", "src_turn_0002"]


def test_merge_gap_beyond_threshold_not_merged():
    hits = [_hit("src", 1, "A", 0.9), _hit("src", 4, "B", 0.7)]  # gap=3 > _ADJACENT_GAP=2
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_different_source_not_merged():
    hits = [_hit("srcA", 1, "A"), _hit("srcB", 2, "B")]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_chronological_order():
    # hit B (turn 3) ranked higher but has earlier turn than hit A (turn 5)
    hits = [_hit("src", 5, "나중발언", 0.9), _hit("src", 3, "이전발언", 0.7)]
    result = _merge_adjacent_hits(hits, gap=2)
    assert len(result) == 1
    assert result[0]["content"].index("이전발언") < result[0]["content"].index("나중발언")


def test_merge_max_chars_exceeded_not_merged():
    long_a = "가" * 700
    long_b = "나" * 700
    hits = [_hit("src", 1, long_a), _hit("src", 2, long_b)]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 2


def test_merge_single_hit_unchanged():
    hits = [_hit("src", 1, "혼자")]
    result = _merge_adjacent_hits(hits)
    assert len(result) == 1
    assert result[0]["content"] == "혼자"
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```
python -m pytest tests/test_retriever_v2.py::test_parse_turn_index_standard -v
```
Expected: `ImportError` 또는 `NameError` (_parse_turn_index 미존재)

- [ ] **Step 3: 구현 — 상수 + 두 함수 추가**

`service/rag/retrieval/retriever.py`에서 `_resolve_agency_filter` 함수 직후에 추가:

```python
_ADJACENT_GAP = 2
_MERGE_MAX_CHARS = 1200


def _parse_turn_index(chunk_id: str) -> int | None:
    import re as _re
    m = _re.search(r"_turn_(\d{4})$", chunk_id or "")
    return int(m.group(1)) if m else None


def _merge_adjacent_hits(hits: list[dict], gap: int = _ADJACENT_GAP) -> list[dict]:
    """같은 source_id에서 turn_index 차이가 gap 이하인 인접 청크를 병합."""
    if len(hits) < 2:
        return list(hits)

    # (source_id, turn_index) → hits 내 인덱스
    turn_map: dict[tuple[str, int], int] = {}
    for i, h in enumerate(hits):
        sid = h.get("source_id") or ""
        tidx = _parse_turn_index(str(h.get("chunk_id") or ""))
        if sid and tidx is not None:
            turn_map[(sid, tidx)] = i

    consumed: set[int] = set()
    result: list[dict] = []

    for i, hit in enumerate(hits):
        if i in consumed:
            continue

        sid = hit.get("source_id") or ""
        tidx = _parse_turn_index(str(hit.get("chunk_id") or ""))

        if not sid or tidx is None:
            result.append(hit)
            continue

        # 가장 가까운 un-consumed 이웃 탐색
        best_j: int | None = None
        best_dist = gap + 1
        for delta in range(1, gap + 1):
            for cand_tidx in (tidx + delta, tidx - delta):
                j = turn_map.get((sid, cand_tidx))
                if j is not None and j != i and j not in consumed:
                    d = abs(cand_tidx - tidx)
                    if d < best_dist:
                        best_j, best_dist = j, d
            if best_j is not None:
                break

        if best_j is None:
            result.append(hit)
            continue

        hit_b = hits[best_j]
        text_a = hit.get("content") or ""
        text_b = hit_b.get("content") or ""

        if len(text_a) + len(text_b) + 2 > _MERGE_MAX_CHARS:
            result.append(hit)
            continue

        # 시간순(turn_index 오름차순)으로 합치기
        tidx_b = _parse_turn_index(str(hit_b.get("chunk_id") or ""))
        if tidx_b is not None and tidx_b < tidx:
            content = text_b.rstrip() + "\n\n" + text_a.lstrip()
        else:
            content = text_a.rstrip() + "\n\n" + text_b.lstrip()

        merged = dict(hit)
        merged["content"] = content
        merged["hybrid_score"] = max(
            float(hit.get("hybrid_score", 0.0)),
            float(hit_b.get("hybrid_score", 0.0)),
        )
        merged["_merged_chunk_ids"] = [
            hit.get("chunk_id", ""),
            hit_b.get("chunk_id", ""),
        ]
        consumed.add(best_j)
        result.append(merged)

    return result
```

참고: 파일 상단에 이미 `import re`가 있으므로 `_merge_adjacent_hits` 안에서 `import re as _re` 대신 모듈 레벨 `re`를 그대로 사용할 수 있다. 구현 시 아래처럼 수정하면 된다:

```python
def _parse_turn_index(chunk_id: str) -> int | None:
    m = re.search(r"_turn_(\d{4})$", chunk_id or "")
    return int(m.group(1)) if m else None
```

(파일 상단 `import re`가 이미 있음)

- [ ] **Step 4: 테스트 실행 → 8개 PASS 확인**

```
python -m pytest tests/test_retriever_v2.py -v -k "parse_turn or merge"
```
Expected: 8 tests PASS

- [ ] **Step 5: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 187 passed (기존 179 + 신규 8)

- [ ] **Step 6: 커밋**

```
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: _merge_adjacent_hits — 인접 청크 병합 함수 추가 (Algorithm #6)"
```

---

### Task 2: `use_smart_merge` 파라미터 wiring — search() + search_v2()

**Files:**
- Modify: `service/rag/retrieval/retriever.py` (search() + search_v2() 파라미터 + 호출 추가)
- Test: `tests/test_retriever_v2.py` (기존 파일 하단에 추가, 2개 테스트)

**Interfaces:**
- Consumes: `_merge_adjacent_hits` (Task 1에서 추가됨)
- Produces:
  - `search(..., use_smart_merge: bool = True) -> list[dict]`
  - `search_v2(..., use_smart_merge: bool = True) -> list[dict]`

- [ ] **Step 1: 테스트 먼저 작성**

`tests/test_retriever_v2.py` 하단에 추가:

```python
import inspect
from service.rag.retrieval.retriever import Retriever


def test_search_signature_has_use_smart_merge():
    sig = inspect.signature(Retriever.search)
    assert "use_smart_merge" in sig.parameters
    assert sig.parameters["use_smart_merge"].default is True


def test_search_v2_signature_has_use_smart_merge():
    sig = inspect.signature(Retriever.search_v2)
    assert "use_smart_merge" in sig.parameters
    assert sig.parameters["use_smart_merge"].default is True
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```
python -m pytest tests/test_retriever_v2.py::test_search_signature_has_use_smart_merge -v
```
Expected: FAIL (파라미터 없음)

- [ ] **Step 3: search()에 파라미터 + 호출 추가**

`service/rag/retrieval/retriever.py`의 `search()` 시그니처에 파라미터 추가 (기존 `agency: str | None = None,` 바로 다음):

```python
        agency: str | None = None,
        use_smart_merge: bool = True,
    ) -> list[dict]:
```

그리고 search() 본문에서 top_k 슬라이싱 **직후**, `# Parent Document Retrieval` 주석 **직전**에 삽입:

```python
        # Smart Chunk Merge — 인접 발언 병합
        if use_smart_merge and out:
            out = _merge_adjacent_hits(out)

        # Parent Document Retrieval — 검색 후 문맥 확장
```

(기존 line 250: `if use_parent_doc and out:` 바로 위)

- [ ] **Step 4: search_v2()에 파라미터 + 호출 추가**

`search_v2()` 시그니처에 파라미터 추가 (기존 `agency: str | None = None,` 바로 다음):

```python
        agency: str | None = None,
        use_smart_merge: bool = True,
    ) -> list[dict]:
```

그리고 search_v2() 본문에서 `return self._enrich_with_context(merged)` 직전에 삽입:

```python
        # Smart Chunk Merge — 인접 발언 병합
        if use_smart_merge and merged:
            merged = _merge_adjacent_hits(merged)
        return self._enrich_with_context(merged)
```

- [ ] **Step 5: 테스트 실행 → 2개 PASS 확인**

```
python -m pytest tests/test_retriever_v2.py::test_search_signature_has_use_smart_merge tests/test_retriever_v2.py::test_search_v2_signature_has_use_smart_merge -v
```
Expected: 2 tests PASS

- [ ] **Step 6: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 189 passed

- [ ] **Step 7: 커밋**

```
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: use_smart_merge 파라미터 wiring — search/search_v2 인접 병합 활성화 (Algorithm #6)"
```

---

### Task 3: `eval/smart_merge_eval.py` 평가 스크립트

**Files:**
- Create: `eval/smart_merge_eval.py`

**Interfaces:**
- Consumes: `_merge_adjacent_hits`, `_ADJACENT_GAP`, `_MERGE_MAX_CHARS` (Task 1), 청크 파일 `data/v2/transform/final/chunks_v2.jsonl`

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


def load_chunks(n: int = MAX_LOAD) -> list[dict]:
    if not CHUNKS_FILE.exists():
        print(f"[smart_merge_eval] chunks file not found: {CHUNKS_FILE}")
        return []
    chunks = []
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
            if len(chunks) >= n:
                break
    return chunks


def simulate_merge(chunks: list[dict], gap: int) -> dict:
    from service.rag.retrieval.retriever import _merge_adjacent_hits, _parse_turn_index

    # source_id 기준 그룹화
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id") or ""
        if sid:
            groups.setdefault(sid, []).append(c)

    total_pairs = 0
    mergeable_pairs = 0
    blocked_by_length = 0

    for sid, grp in groups.items():
        grp.sort(key=lambda x: _parse_turn_index(str(x.get("chunk_id") or "")) or 0)
        for i in range(len(grp) - 1):
            tidx_a = _parse_turn_index(str(grp[i].get("chunk_id") or ""))
            tidx_b = _parse_turn_index(str(grp[i + 1].get("chunk_id") or ""))
            if tidx_a is None or tidx_b is None:
                continue
            total_pairs += 1
            dist = tidx_b - tidx_a
            if dist <= gap:
                len_a = len(grp[i].get("clean_text") or grp[i].get("content") or "")
                len_b = len(grp[i + 1].get("clean_text") or grp[i + 1].get("content") or "")
                if len_a + len_b + 2 <= 1200:
                    mergeable_pairs += 1
                else:
                    blocked_by_length += 1

    return {
        "total_chunks": len(chunks),
        "total_consecutive_pairs": total_pairs,
        "mergeable_pairs": mergeable_pairs,
        "blocked_by_length": blocked_by_length,
        "merge_rate": mergeable_pairs / max(total_pairs, 1),
    }


def demo_merge(chunks: list[dict]) -> None:
    from service.rag.retrieval.retriever import _merge_adjacent_hits, _parse_turn_index

    # 같은 source_id에서 연속 turn을 가진 청크 쌍 찾기
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id") or ""
        if sid:
            groups.setdefault(sid, []).append(c)

    sample_hits: list[dict] = []
    for sid, grp in groups.items():
        grp.sort(key=lambda x: _parse_turn_index(str(x.get("chunk_id") or "")) or 0)
        for i in range(len(grp) - 1):
            tidx_a = _parse_turn_index(str(grp[i].get("chunk_id") or ""))
            tidx_b = _parse_turn_index(str(grp[i + 1].get("chunk_id") or ""))
            if tidx_a is None or tidx_b is None:
                continue
            if tidx_b - tidx_a <= 2:
                # 두 청크를 hit 형태로 변환
                def _to_hit(c: dict, score: float) -> dict:
                    return {
                        "chunk_id": c.get("chunk_id", ""),
                        "source_id": c.get("source_id", ""),
                        "content": c.get("clean_text") or c.get("content") or "",
                        "hybrid_score": score,
                        "speaker": c.get("speaker", ""),
                    }
                sample_hits = [_to_hit(grp[i], 0.9), _to_hit(grp[i + 1], 0.7)]
                break
        if sample_hits:
            break

    if not sample_hits:
        print("  (연속 청크 샘플 없음)")
        return

    print("병합 전:")
    for h in sample_hits:
        print(f"  [{h['chunk_id']}] score={h['hybrid_score']}")
        print(f"  {(h['content'])[:120]}...")
        print()

    merged = _merge_adjacent_hits(sample_hits)
    print("병합 후:")
    for h in merged:
        ids = h.get("_merged_chunk_ids", [h.get("chunk_id")])
        print(f"  [{' + '.join(ids)}] score={h['hybrid_score']:.2f}")
        print(f"  {h['content'][:250]}...")
        print()


def main() -> None:
    chunks = load_chunks()
    print(f"[smart_merge_eval] loaded {len(chunks)} chunks")
    print()

    from service.rag.retrieval.retriever import _ADJACENT_GAP, _MERGE_MAX_CHARS
    print(f"파라미터: GAP={_ADJACENT_GAP}, MAX_CHARS={_MERGE_MAX_CHARS}")
    print()

    print(sep)
    print("=== 병합 가능 쌍 통계 ===")
    stats = simulate_merge(chunks, gap=_ADJACENT_GAP)
    print(f"  총 청크 수              : {stats['total_chunks']:,}")
    print(f"  연속 청크 쌍(분석 대상) : {stats['total_consecutive_pairs']:,}")
    print(f"  병합 가능 쌍            : {stats['mergeable_pairs']:,}  ({stats['merge_rate']:.1%})")
    print(f"  길이 초과로 미병합      : {stats['blocked_by_length']:,}")
    print()

    print(sep)
    print("=== 병합 전/후 미리보기 ===")
    demo_merge(chunks)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 검증**

```
python -c "import ast; ast.parse(open('eval/smart_merge_eval.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 전체 테스트 통과 확인**

```
python -m pytest tests/ -q
```
Expected: 189 passed

- [ ] **Step 4: 커밋**

```
git add eval/smart_merge_eval.py
git commit -m "eval: smart_merge_eval 스크립트 추가 (Algorithm #6)"
```

---

## Self-Review

### 1. Spec Coverage

| 요구사항 | 태스크 |
|---|---|
| `_parse_turn_index` 구현 | Task 1 |
| `_merge_adjacent_hits` 구현 | Task 1 |
| `_ADJACENT_GAP`, `_MERGE_MAX_CHARS` 상수 | Task 1 |
| 병합 조건: 같은 source_id + gap ≤ 2 | Task 1 (step 3) |
| 합산 길이 ≤ 1200 chars | Task 1 (step 3) |
| content 시간순 결합 | Task 1 (step 3) |
| hybrid_score = max | Task 1 (step 3) |
| `_merged_chunk_ids` 필드 | Task 1 (step 3) |
| `use_smart_merge: bool = True` in search() | Task 2 |
| `use_smart_merge: bool = True` in search_v2() | Task 2 |
| 적용 위치: top_k 슬라이싱 직후, parent_doc 직전 (search) | Task 2 |
| 적용 위치: _enrich_with_context 직전 (search_v2) | Task 2 |
| qa_pair 청크 자동 미병합 (chunk_id에 `_turn_` 없음) | Task 1 test `test_parse_turn_index_none_for_qa` |
| eval 스크립트 | Task 3 |

### 2. Placeholder 스캔

없음.

### 3. Type Consistency

- `_parse_turn_index(chunk_id: str) -> int | None` — Task 1에서 정의, Task 2의 tests에서 사용
- `_merge_adjacent_hits(hits: list[dict], gap: int = _ADJACENT_GAP) -> list[dict]` — Task 1에서 정의, Task 2 wiring에서 호출
- 모든 Task에서 `_ADJACENT_GAP`, `_MERGE_MAX_CHARS` 동일 이름 사용

✅ 일관성 확인 완료.
