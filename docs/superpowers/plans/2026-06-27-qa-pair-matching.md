# Q&A Pair Matching Algorithm — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ETL 파이프라인에 `qa_pairer_v2.py` 단계를 추가해 회의록의 "질의→답변" 쌍을 자동으로 구성하고, 검색 시 쌍 단위로 리트리벌하여 `qa_pair_extract` 품질을 높인다.

**Architecture:**
chunker_v2가 생성한 청크 목록을 상태 기계(state machine)로 순차 스캔해 QUESTIONING→ANSWERING 전환을 감지, QA 쌍 레코드를 생성한다. QA 쌍은 `section_type='body'`, `metadata.chunk_type='qa_pair'`로 `chunks_v2` 테이블에 upsert되어 기존 임베딩 파이프라인에 자연스럽게 편입된다. 일반 검색은 기본적으로 `chunk_type='utterance'`만 사용하고, `qa_pair_extract` 질문에서는 `chunk_type='qa_pair'`만 사용한다.

**Tech Stack:** Python 3.11+, PostgreSQL 16 + pgvector, psycopg2, 기존 BGE-M3 임베딩 모델

## Global Constraints

- 기존 `chunks_v2` 테이블 컬럼 구조는 변경하지 않는다 (ALTER TABLE 없음)
- `chunk_type` 구분은 `metadata` JSONB 필드 내 키로만 관리한다
- `section_type = 'body'` 조건은 모든 쿼리에서 유지한다
- 기존 `utterance` 청크의 메타데이터/임베딩은 건드리지 않는다
- 모든 새 레코드의 `chunk_id`는 `{source_id}_qa_{pair_index:04d}` 형식이다
- 파이썬 타입 힌트 필수, `from __future__ import annotations` 첫 줄

---

## 알고리즘 상세 설계

### 상태 기계 전환 규칙

```
상태: IDLE | QUESTIONING | ANSWERING

IDLE:
  utterance_type == "question"  →  QUESTIONING, q_group = [turn]
  otherwise                     →  IDLE

QUESTIONING:
  utterance_type == "question"  →  QUESTIONING, q_group.append(turn)  # 추가 질의
  utterance_type == "answer"    →  ANSWERING,   a_group = [turn]
  utterance_type == "procedural" → IDLE,  q_group 폐기 (답변 없는 질의)
  turn_index_gap > MAX_GAP(8)   →  IDLE,  q_group 폐기

ANSWERING:
  utterance_type == "answer"    →  ANSWERING, a_group.append(turn)    # 추가 답변
  utterance_type == "question"  →  emit 현재 pair → QUESTIONING, q_group = [turn]
  utterance_type == "procedural" → emit 현재 pair → IDLE
  turn_index_gap > MAX_GAP(8)   →  emit 현재 pair → IDLE

emit:
  if q_group and a_group:
    create qa_pair record
  q_group = [], a_group = []
```

### QA 쌍 레코드 구조

```python
{
  "chunk_id": f"{source_id}_qa_{pair_index:04d}",
  "source_id": source_id,
  "page_no": q_group[0]["page_no"],
  "turn_index": q_group[0]["turn_index"],
  "section_type": "body",
  "speaker": f"{q_speaker} → {a_speaker}",        # "이재정 → 조태열"
  "speaker_role": f"{q_role} → {a_role}",
  "raw_text": clean_text,                           # clean_text와 동일
  "clean_text": "[질의]\n{q_text}\n\n[답변]\n{a_text}",
  "embed_text": "[회의일: ...] [위원회: ...] [질의자: ...] [답변자: ...]\n[질의]\n...\n[답변]\n...",
  "metadata": {
    "chunk_type": "qa_pair",
    "utterance_type": "qa_pair",
    "question_speaker": q_speaker,
    "question_role": q_role,
    "answer_speaker": a_speaker,
    "answer_role": a_role,
    "question_turn_indices": [t["turn_index"] for t in q_group],
    "answer_turn_indices":   [t["turn_index"] for t in a_group],
    # 공유 메타 (첫 q_turn에서 복사)
    "committee": ..., "meeting_date": ..., "party": q_party,
    "question_type_hints": ["qa_pair_extract", "topic_search",
                            "source_check", "report_generation"],
    "token_count": token_count,
  }
}
```

---

## 파일 구조

| 파일 | 작업 |
|---|---|
| `service/etl/transform/qa_pairer_v2.py` | **신규** — 상태 기계 + QA 레코드 생성 |
| `service/etl/run_pipeline_v2.py` | **수정** — step [5/7] qa_pairer 추가 |
| `service/rag/vectorstore/pgvector_store.py` | **수정** — chunk_type 필터 추가 |
| `tests/test_qa_pairer_v2.py` | **신규** — 상태 기계 단위 테스트 |

---

## Task 1: 상태 기계 핵심 로직 + 단위 테스트

**Files:**
- Create: `service/etl/transform/qa_pairer_v2.py`
- Test: `tests/test_qa_pairer_v2.py`

**Interfaces:**
- Produces:
  - `pair_qa_chunks(chunks: list[dict]) -> list[dict]` — 청크 목록에서 QA 쌍 생성
  - `main() -> None` — CLI 진입점, `data/v2/transform/final/chunks_v2.jsonl` 읽어 `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl` 출력

---

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_qa_pairer_v2.py` 파일 생성:

```python
from __future__ import annotations
import pytest
from service.etl.transform.qa_pairer_v2 import pair_qa_chunks

def _turn(source_id, turn_index, utterance_type, speaker, speaker_role,
          position_type, text, page_no=1, meeting_date="2024-10-15", committee="외교통일위원회"):
    return {
        "chunk_id": f"{source_id}_turn_{turn_index:04d}",
        "source_id": source_id,
        "turn_index": turn_index,
        "page_no": page_no,
        "section_type": "body",
        "speaker": speaker,
        "speaker_role": speaker_role,
        "clean_text": text,
        "raw_text": text,
        "embed_text": text,
        "metadata": {
            "utterance_type": utterance_type,
            "position_type": position_type,
            "committee": committee,
            "meeting_date": meeting_date,
            "party": "더불어민주당" if position_type == "의원" else "정부",
            "question_type_hints": ["qa_pair_extract"] if utterance_type in ("question", "answer") else [],
        },
    }


# ── 케이스 1: 단순 Q→A 1쌍 ──────────────────────────────────────
def test_simple_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "대북제재 입장이 어떻습니까?"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "제재 기조 유지하겠습니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["metadata"]["chunk_type"] == "qa_pair"
    assert p["metadata"]["question_speaker"] == "이재정"
    assert p["metadata"]["answer_speaker"] == "조태열"
    assert "[질의]" in p["clean_text"]
    assert "[답변]" in p["clean_text"]
    assert p["chunk_id"].startswith("SRC1_qa_")


# ── 케이스 2: 연속 질의 (같은 질의자) → 1쌍 ─────────────────────
def test_multi_question_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "첫째 질의입니다."),
        _turn("SRC1", 1, "question", "이재정", "위원", "의원", "둘째 질의입니다."),
        _turn("SRC1", 2, "answer",   "조태열", "장관", "정부측", "두 질의에 답합니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    assert "첫째 질의입니다." in pairs[0]["clean_text"]
    assert "둘째 질의입니다." in pairs[0]["clean_text"]


# ── 케이스 3: 연속 답변 (같은 답변자) → 1쌍 ─────────────────────
def test_multi_answer_one_pair():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "질의입니다."),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "첫째 답변입니다."),
        _turn("SRC1", 2, "answer",   "조태열", "장관", "정부측", "둘째 답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
    assert "첫째 답변입니다." in pairs[0]["clean_text"]
    assert "둘째 답변입니다." in pairs[0]["clean_text"]


# ── 케이스 4: 두 개의 독립적인 Q-A 쌍 ───────────────────────────
def test_two_independent_pairs():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "첫 질의"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "첫 답변"),
        _turn("SRC1", 2, "question", "김석기", "위원", "의원", "둘째 질의"),
        _turn("SRC1", 3, "answer",   "조태열", "장관", "정부측", "둘째 답변"),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 2
    assert pairs[0]["metadata"]["question_speaker"] == "이재정"
    assert pairs[1]["metadata"]["question_speaker"] == "김석기"


# ── 케이스 5: 답변 없는 질의 (procedural이 끊음) → 0쌍 ──────────
def test_unanswered_question_emits_nothing():
    turns = [
        _turn("SRC1", 0, "question",   "이재정", "위원", "의원", "질의합니다."),
        _turn("SRC1", 1, "procedural", "김석기", "위원장", "위원장", "잠시 정회하겠습니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 6: 고아 답변 (질의 없는 답변) → 0쌍 ──────────────────
def test_orphan_answer_skipped():
    turns = [
        _turn("SRC1", 0, "answer", "조태열", "장관", "정부측", "보충 답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 7: turn_index 갭 > 8 → 질의가 폐기됨 ─────────────────
def test_large_gap_discards_question():
    turns = [
        _turn("SRC1", 0,  "question", "이재정", "위원", "의원", "질의합니다."),
        _turn("SRC1", 10, "answer",   "조태열", "장관", "정부측", "답변입니다."),
    ]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


# ── 케이스 8: 빈 입력 ───────────────────────────────────────────
def test_empty_input():
    assert pair_qa_chunks([]) == []


# ── 케이스 9: chunk_id 형식 검증 ───────────────────────────────
def test_chunk_id_format():
    turns = [
        _turn("DOC_001", 0, "question", "이재정", "위원", "의원", "질의"),
        _turn("DOC_001", 1, "answer",   "조태열", "장관", "정부측", "답변"),
        _turn("DOC_001", 2, "question", "김석기", "위원", "의원", "질의2"),
        _turn("DOC_001", 3, "answer",   "조태열", "장관", "정부측", "답변2"),
    ]
    pairs = pair_qa_chunks(turns)
    assert pairs[0]["chunk_id"] == "DOC_001_qa_0000"
    assert pairs[1]["chunk_id"] == "DOC_001_qa_0001"


# ── 케이스 10: embed_text에 필수 메타 포함 ─────────────────────
def test_embed_text_contains_meta():
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원", "질의"),
        _turn("SRC1", 1, "answer",   "조태열", "장관", "정부측", "답변"),
    ]
    pairs = pair_qa_chunks(turns)
    embed = pairs[0]["embed_text"]
    assert "외교통일위원회" in embed
    assert "2024-10-15" in embed
    assert "이재정" in embed
    assert "조태열" in embed
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```
pytest tests/test_qa_pairer_v2.py -v 2>&1 | head -20
```

Expected: `ERROR` — `service.etl.transform.qa_pairer_v2` 모듈 없음

- [ ] **Step 3: 핵심 구현 작성**

`service/etl/transform/qa_pairer_v2.py` 파일 생성:

```python
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHUNKS_FINAL = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"
OUT_DIR       = ROOT / "data" / "v2" / "transform" / "qa_pairs"
OUT_FILE      = OUT_DIR / "qa_pairs_v2.jsonl"

MAX_GAP = 8  # turn_index 갭이 이보다 크면 Q-A 연결 단절로 간주


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 2)


def _concat_texts(turns: list[dict]) -> str:
    parts = []
    for t in turns:
        speaker = t.get("speaker", "")
        text    = (t.get("clean_text") or "").strip()
        parts.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(parts)


def _make_clean_text(q_group: list[dict], a_group: list[dict]) -> str:
    return f"[질의]\n{_concat_texts(q_group)}\n\n[답변]\n{_concat_texts(a_group)}"


def _make_embed_text(q_group: list[dict], a_group: list[dict]) -> str:
    meta = q_group[0].get("metadata", {})
    date      = meta.get("meeting_date", "")
    committee = meta.get("committee", "")
    q_speaker = q_group[0].get("speaker", "")
    q_role    = q_group[0].get("speaker_role", "")
    a_speaker = a_group[0].get("speaker", "")
    a_role    = a_group[0].get("speaker_role", "")
    q_party   = meta.get("party", "")

    q_label = f"{q_speaker} {q_role}".strip()
    if q_party and q_party not in ("정부", "미확인", ""):
        q_label += f" ({q_party})"
    a_label = f"{a_speaker} {a_role}".strip()

    header_parts = []
    if date:
        header_parts.append(f"[회의일: {date}]")
    if committee:
        header_parts.append(f"[위원회: {committee}]")
    if q_label:
        header_parts.append(f"[질의자: {q_label}]")
    if a_label:
        header_parts.append(f"[답변자: {a_label}]")
    header_parts.append("[발화유형: 질의-답변 쌍]")

    header = " ".join(header_parts)
    body   = _make_clean_text(q_group, a_group)
    return f"{header}\n{body}".strip()


def _make_qa_record(
    source_id: str,
    pair_index: int,
    q_group: list[dict],
    a_group: list[dict],
) -> dict:
    q0   = q_group[0]
    a0   = a_group[0]
    meta = dict(q0.get("metadata", {}))

    clean = _make_clean_text(q_group, a_group)
    embed = _make_embed_text(q_group, a_group)

    q_speaker = q0.get("speaker", "")
    q_role    = q0.get("speaker_role", "")
    a_speaker = a0.get("speaker", "")
    a_role    = a0.get("speaker_role", "")

    meta.update({
        "chunk_type":            "qa_pair",
        "utterance_type":        "qa_pair",
        "question_speaker":      q_speaker,
        "question_role":         q_role,
        "answer_speaker":        a_speaker,
        "answer_role":           a_role,
        "question_turn_indices": [t["turn_index"] for t in q_group],
        "answer_turn_indices":   [t["turn_index"] for t in a_group],
        "question_type_hints":   ["qa_pair_extract", "topic_search",
                                  "source_check", "report_generation"],
        "token_count":           _count_tokens(clean),
    })

    return {
        "chunk_id":    f"{source_id}_qa_{pair_index:04d}",
        "source_id":   source_id,
        "page_no":     q0.get("page_no"),
        "turn_index":  q0.get("turn_index"),
        "section_type": "body",
        "speaker":      f"{q_speaker} → {a_speaker}",
        "speaker_role": f"{q_role} → {a_role}",
        "raw_text":     clean,
        "clean_text":   clean,
        "embed_text":   embed,
        "metadata":     meta,
    }


def pair_qa_chunks(chunks: list[dict]) -> list[dict]:
    """
    청크 목록(단일 source_id 가정)을 순차 스캔해 Q-A 쌍 레코드를 반환한다.
    여러 source_id가 섞인 경우에도 source_id 경계를 자동으로 감지해 처리한다.
    """
    if not chunks:
        return []

    # source_id별 그룹 분리
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        sid = c.get("source_id", "")
        groups.setdefault(sid, []).append(c)

    all_pairs: list[dict] = []
    for sid, sid_chunks in groups.items():
        sid_chunks = sorted(sid_chunks, key=lambda c: c.get("turn_index", 0))
        all_pairs.extend(_pair_single_source(sid, sid_chunks))

    return all_pairs


def _pair_single_source(source_id: str, chunks: list[dict]) -> list[dict]:
    # qa_pair 레코드는 처리에서 제외 (재실행 시 중복 방지)
    utterance_chunks = [
        c for c in chunks
        if c.get("metadata", {}).get("chunk_type", "utterance") == "utterance"
    ]

    pairs: list[dict] = []
    pair_index = 0

    q_group: list[dict] = []
    a_group: list[dict] = []
    state = "IDLE"   # IDLE | QUESTIONING | ANSWERING

    def _emit() -> None:
        nonlocal pair_index
        if q_group and a_group:
            pairs.append(_make_qa_record(source_id, pair_index, q_group[:], a_group[:]))
            pair_index += 1

    def _gap(prev: dict | None, curr: dict) -> int:
        if prev is None:
            return 0
        return abs(curr.get("turn_index", 0) - prev.get("turn_index", 0))

    prev_chunk: dict | None = None

    for chunk in utterance_chunks:
        utterance_type = chunk.get("metadata", {}).get("utterance_type", "statement")
        gap = _gap(prev_chunk, chunk)

        # ── 갭 초과 처리 ────────────────────────────────────────────
        if gap > MAX_GAP and state != "IDLE":
            if state == "ANSWERING":
                _emit()
            # QUESTIONING이면 답변 없는 질의 → 폐기
            q_group.clear()
            a_group.clear()
            state = "IDLE"

        # ── 상태 전환 ────────────────────────────────────────────────
        if state == "IDLE":
            if utterance_type == "question":
                q_group = [chunk]
                state = "QUESTIONING"

        elif state == "QUESTIONING":
            if utterance_type == "question":
                q_group.append(chunk)
            elif utterance_type == "answer":
                a_group = [chunk]
                state = "ANSWERING"
            elif utterance_type == "procedural":
                # 답변 없는 질의 — 폐기
                q_group.clear()
                state = "IDLE"

        elif state == "ANSWERING":
            if utterance_type == "answer":
                a_group.append(chunk)
            elif utterance_type == "question":
                _emit()
                q_group = [chunk]
                a_group = []
                state = "QUESTIONING"
            elif utterance_type == "procedural":
                _emit()
                q_group.clear()
                a_group.clear()
                state = "IDLE"

        prev_chunk = chunk

    # 마지막 쌍 처리
    if state == "ANSWERING":
        _emit()

    return pairs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []
    if not CHUNKS_FINAL.exists():
        print(f"[qa_pairer_v2] 청크 파일 없음: {CHUNKS_FINAL}")
        return

    with CHUNKS_FINAL.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_chunks.append(json.loads(line))

    pairs = pair_qa_chunks(all_chunks)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"[qa_pairer_v2] qa_pairs={len(pairs)} → {OUT_FILE}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 및 통과 확인**

```
pytest tests/test_qa_pairer_v2.py -v
```

Expected (전체 통과):
```
tests/test_qa_pairer_v2.py::test_simple_one_pair PASSED
tests/test_qa_pairer_v2.py::test_multi_question_one_pair PASSED
tests/test_qa_pairer_v2.py::test_multi_answer_one_pair PASSED
tests/test_qa_pairer_v2.py::test_two_independent_pairs PASSED
tests/test_qa_pairer_v2.py::test_unanswered_question_emits_nothing PASSED
tests/test_qa_pairer_v2.py::test_orphan_answer_skipped PASSED
tests/test_qa_pairer_v2.py::test_large_gap_discards_question PASSED
tests/test_qa_pairer_v2.py::test_empty_input PASSED
tests/test_qa_pairer_v2.py::test_chunk_id_format PASSED
tests/test_qa_pairer_v2.py::test_embed_text_contains_meta PASSED
```

- [ ] **Step 5: 커밋**

```bash
git add service/etl/transform/qa_pairer_v2.py tests/test_qa_pairer_v2.py
git commit -m "feat: Q&A pairing algorithm — state machine pairs question→answer turns"
```

---

## Task 2: 파이프라인 통합 — qa_pairer를 ETL에 연결

**Files:**
- Modify: `service/etl/run_pipeline_v2.py`

**Interfaces:**
- Consumes: `pair_qa_chunks(chunks)` from Task 1
- Produces: `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl` (Task 3 로더가 읽음)

---

- [ ] **Step 1: 실패하는 통합 테스트 작성**

`tests/test_qa_pairer_v2.py` 파일 하단에 추가:

```python
# ── 통합: main() 함수가 JSONL 파일을 읽고 출력 생성 ─────────────
def test_main_creates_output(tmp_path, monkeypatch):
    import json
    from service.etl.transform import qa_pairer_v2

    # 임시 입력 파일 생성
    input_file = tmp_path / "chunks_v2.jsonl"
    output_dir = tmp_path / "qa_pairs"
    turns = [
        _turn("S1", 0, "question", "이재정", "위원", "의원", "질의"),
        _turn("S1", 1, "answer",   "조태열", "장관", "정부측", "답변"),
    ]
    with input_file.open("w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 경로 패치
    monkeypatch.setattr(qa_pairer_v2, "CHUNKS_FINAL", input_file)
    monkeypatch.setattr(qa_pairer_v2, "OUT_DIR",  output_dir)
    monkeypatch.setattr(qa_pairer_v2, "OUT_FILE", output_dir / "qa_pairs_v2.jsonl")

    qa_pairer_v2.main()

    out = output_dir / "qa_pairs_v2.jsonl"
    assert out.exists()
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["metadata"]["chunk_type"] == "qa_pair"
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_qa_pairer_v2.py::test_main_creates_output -v
```

Expected: FAIL (monkeypatch 대상 경로가 존재하지 않거나 JSONL 없음)

- [ ] **Step 3: run_pipeline_v2.py 수정**

`service/etl/run_pipeline_v2.py` 전체 교체:

```python
from __future__ import annotations

from service.etl.extractor import extractor_v2
from service.etl.transform import normalizer_v2, parser_v2, chunker_v2, qa_pairer_v2
from service.etl.loader import jsonl_to_postgres_v2, embeddings_v2


def run_etl() -> None:
    """ETL 5단계: JSONL 산출물 생성."""
    print("=== ETL v2 파이프라인 시작 ===\n")
    print("[1/5] extractor_v2 — page별 raw_text 추출")
    extractor_v2.main()
    print("\n[2/5] normalizer_v2 — 잡음 제거 + section_type")
    normalizer_v2.main()
    print("\n[3/5] parser_v2 — speaker turn 구조화")
    parser_v2.main()
    print("\n[4/5] chunker_v2 — 짧은 turn 병합 + embed_text")
    chunker_v2.main()
    print("\n[5/5] qa_pairer_v2 — 질의-답변 쌍 생성")
    qa_pairer_v2.main()
    print("\n=== ETL v2 완료 ===")


def run_load() -> None:
    """적재 2단계: chunks_v2 → embeddings_e5_v2."""
    print("\n=== 적재 v2 시작 ===\n")
    print("[6/7] jsonl_to_postgres_v2 — chunks_v2 테이블 upsert")
    jsonl_to_postgres_v2.main()
    print("\n[7/7] embeddings_v2 — embed_text 임베딩")
    embeddings_v2.main()
    print("\n=== 적재 v2 완료 ===")


def run() -> None:
    """전체 파이프라인: ETL + 적재 + 임베딩."""
    run_etl()
    run_load()


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_qa_pairer_v2.py -v
```

Expected: 전체 11개 PASS

- [ ] **Step 5: 커밋**

```bash
git add service/etl/run_pipeline_v2.py tests/test_qa_pairer_v2.py
git commit -m "feat: add qa_pairer_v2 as step 5 in ETL pipeline"
```

---

## Task 3: DB 적재 — QA 쌍을 chunks_v2에 upsert

**Files:**
- Modify: `service/etl/loader/jsonl_to_postgres_v2.py`

**Interfaces:**
- Consumes: `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl`
- Produces: `chunks_v2` 테이블에 `chunk_type='qa_pair'` 레코드 upsert

---

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_jsonl_to_postgres_v2.py` 파일을 읽고 하단에 추가한다:

```python
def test_load_qa_pairs_calls_load_with_qa_path(monkeypatch, tmp_path):
    """load_chunks_v2가 qa_pairs 파일도 처리하는지 확인 (실제 DB 없이 경로 검증)."""
    import json
    from service.etl.loader import jsonl_to_postgres_v2

    qa_file = tmp_path / "qa_pairs_v2.jsonl"
    qa_file.write_text(
        json.dumps({
            "chunk_id": "S1_qa_0000", "source_id": "S1",
            "page_no": 1, "turn_index": 0, "section_type": "body",
            "speaker": "이재정 → 조태열", "speaker_role": "위원 → 장관",
            "raw_text": "[질의]\n질의\n\n[답변]\n답변",
            "clean_text": "[질의]\n질의\n\n[답변]\n답변",
            "embed_text": "[회의일: 2024-10-15] 질의 답변",
            "metadata": {"chunk_type": "qa_pair", "utterance_type": "qa_pair",
                         "committee": "외교통일위원회", "meeting_date": "2024-10-15"},
        }, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    inserted = []

    def fake_load(jsonl_path=None, batch_size=1000):
        if jsonl_path:
            inserted.append(str(jsonl_path))
        return True

    monkeypatch.setattr(jsonl_to_postgres_v2, "load_chunks_v2", fake_load)
    jsonl_to_postgres_v2.load_qa_pairs(qa_file)
    assert str(qa_file) in inserted
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_jsonl_to_postgres_v2.py::test_load_qa_pairs_calls_load_with_qa_path -v
```

Expected: FAIL — `load_qa_pairs` 함수 없음

- [ ] **Step 3: jsonl_to_postgres_v2.py 수정**

`service/etl/loader/jsonl_to_postgres_v2.py` 하단에 추가 (기존 코드는 유지):

```python
DEFAULT_QA_JSONL = ROOT / "data" / "v2" / "transform" / "qa_pairs" / "qa_pairs_v2.jsonl"


def load_qa_pairs(jsonl_path: Path | None = None, batch_size: int = 1000) -> bool:
    """QA 쌍 JSONL을 chunks_v2에 upsert. 기존 load_chunks_v2 재사용."""
    path = Path(jsonl_path) if jsonl_path else DEFAULT_QA_JSONL
    if not path.exists():
        print(f"[loader_v2] QA 쌍 파일 없음 (스킵): {path}")
        return True  # 파일 없음은 에러가 아님 (첫 실행 등)
    return load_chunks_v2(jsonl_path=path, batch_size=batch_size)


def main() -> None:
    load_chunks_v2()
    load_qa_pairs()
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_jsonl_to_postgres_v2.py -v
```

Expected: 기존 테스트 + 신규 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add service/etl/loader/jsonl_to_postgres_v2.py tests/test_jsonl_to_postgres_v2.py
git commit -m "feat: load_qa_pairs upserts QA pair records into chunks_v2"
```

---

## Task 4: 검색 통합 — chunk_type 필터로 qa_pair 분리

**Files:**
- Modify: `service/rag/vectorstore/pgvector_store.py` (`_build_v2_filter_where` 함수)

**Interfaces:**
- Consumes: `filters.get("chunk_type")` — `"qa_pair"` | `"utterance"` | `None`(기본 = utterance)
- Produces: WHERE 절에 `COALESCE(c.metadata->>'chunk_type','utterance') = %s` 조건 추가

**설계 원칙:**
- `chunk_type` 파라미터 없음 또는 `None` → `'utterance'`로 간주 (기존 검색에 qa_pair 유입 방지)
- `chunk_type='qa_pair'` → qa_pair 레코드만 검색
- `qa_pair_extract` 질문 유형이 들어올 때 retriever가 `chunk_type='qa_pair'`를 filters에 추가해야 함

---

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_pgvector_store_v2.py`를 읽고 하단에 추가한다:

```python
def test_build_v2_filter_default_excludes_qa_pairs():
    """chunk_type 필터 없을 때 기본으로 utterance만 선택."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where({})
    assert "chunk_type" in sql
    assert "utterance" in params


def test_build_v2_filter_qa_pair_mode():
    """chunk_type='qa_pair' 지정 시 qa_pair 레코드만 선택."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where({"chunk_type": "qa_pair"})
    assert "chunk_type" in sql
    assert "qa_pair" in params


def test_build_v2_filter_none_defaults_to_utterance():
    """filters=None 일 때도 utterance 기본 적용."""
    from service.rag.vectorstore.pgvector_store import _build_v2_filter_where
    sql, params = _build_v2_filter_where(None)
    assert "chunk_type" in sql
    assert "utterance" in params
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_pgvector_store_v2.py::test_build_v2_filter_default_excludes_qa_pairs tests/test_pgvector_store_v2.py::test_build_v2_filter_qa_pair_mode tests/test_pgvector_store_v2.py::test_build_v2_filter_none_defaults_to_utterance -v
```

Expected: FAIL (chunk_type 필터 없음)

- [ ] **Step 3: _build_v2_filter_where 수정**

`service/rag/vectorstore/pgvector_store.py`의 `_build_v2_filter_where` 함수 하단 `return` 전에 추가:

```python
    # chunk_type: 기본값 'utterance' (qa_pair가 일반 검색에 혼입되지 않도록)
    chunk_type = str(filters.get("chunk_type") or "utterance").strip() if filters else "utterance"
    parts.append("COALESCE(c.metadata->>'chunk_type', 'utterance') = %s")
    params.append(chunk_type)
```

기존 `return " AND ".join(parts), params` 바로 위에 삽입한다.

- [ ] **Step 4: retriever.search_v2에서 chunk_type 주입**

`service/rag/retrieval/retriever.py`의 `search_v2` 메서드(line ~389)에서 `filters` 딕셔너리를 구성하는 블록을 찾아 `chunk_type` 필드를 추가한다:

```python
# search_v2 내부 (line 390 근처) — 기존 filters 딕셔너리를 아래로 교체
filters = {
    "committee": committee or "",
    "date_from": df or "",
    "date_to": dt or "",
    "speaker": speaker or "",
    "require_speaker": require_speaker,
    "question_type": question_type or "",
    "utterance_type": utterance_type or "",
    "party": party or "",
    "position_type": position_type or "",
    "agency": agency or "",
    # qa_pair_extract 질문 유형이면 qa_pair 청크만, 그 외엔 utterance 청크만
    "chunk_type": "qa_pair" if (question_type or "").strip() == "qa_pair_extract" else "utterance",
}
```

같은 파일의 `search` 메서드(line ~120)도 동일하게 수정:

```python
filters = {
    "committee": committee or "",
    "date_from": df or "",
    "date_to": dt or "",
    "speaker": speaker or "",
    "require_speaker": require_speaker,
    "question_type": question_type or "",
    "utterance_type": utterance_type or "",
    "party": party or "",
    "position_type": position_type or "",
    "agency": agency or "",
    "chunk_type": "qa_pair" if (question_type or "").strip() == "qa_pair_extract" else "utterance",
}
```

- [ ] **Step 5: 테스트 통과 확인**

```
pytest tests/test_pgvector_store_v2.py -v
```

Expected: 기존 + 신규 3개 테스트 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add service/rag/vectorstore/pgvector_store.py service/rag/retrieval/retriever.py
git commit -m "feat: chunk_type filter — qa_pairs excluded from default search, activated for qa_pair_extract"
```

---

## Self-Review

### 스펙 커버리지 체크

| 요구사항 | 구현 태스크 |
|---|---|
| QUESTIONING→ANSWERING 상태 기계 | Task 1 |
| 연속 질의 / 연속 답변 그룹화 | Task 1 (케이스 2, 3) |
| 답변 없는 질의 폐기 | Task 1 (케이스 5) |
| 고아 답변 무시 | Task 1 (케이스 6) |
| turn_index 갭 단절 | Task 1 (케이스 7) |
| QA 쌍 레코드 구조 (chunk_id, embed_text 등) | Task 1 |
| ETL 파이프라인 5단계 추가 | Task 2 |
| chunks_v2 테이블 upsert | Task 3 |
| 기존 검색에서 qa_pair 격리 | Task 4 |
| qa_pair_extract 시 qa_pair만 검색 | Task 4 |

### 누락 없음 확인

- `chunk_type` 필터가 기존 임베딩 파이프라인(`embeddings_v2.py`)에 영향을 주는가?  
  → `WHERE section_type='body'` 조건은 그대로이고 qa_pair도 `section_type='body'`이므로 자동 포함. 변경 불필요.

- `source_id`가 다른 청크가 `pair_qa_chunks`에 섞여 들어올 수 있는가?  
  → `_pair_single_source`에서 source_id별 분리 처리. 안전.

- qa_pair chunk_id가 utterance chunk_id와 충돌하는가?  
  → utterance: `{source_id}_turn_{n:04d}`, qa_pair: `{source_id}_qa_{n:04d}` → 충돌 없음.
