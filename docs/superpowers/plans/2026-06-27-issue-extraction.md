# Algorithm #3: 핵심 쟁점 추출 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 각 발화 청크에 `issue_score`(0.0–1.0)를 부여하고, `issue_extract` 질문 유형 검색 시 고득점 청크가 상위에 노출되도록 리트리버를 개선한다.

**Architecture:** `question_types.py`에 `infer_issue_score()` 규칙 기반 함수를 추가해 쟁점 신호(비리·낭비·위반 패턴, 수치형 고발, 개선 요구)를 점수화한다. `chunker_v2.py`가 이 점수를 `metadata["issue_score"]`에 저장한다. 리트리버(`retriever.py`)는 `issue_extract` 질문 유형일 때 `_apply_issue_boost()`로 `hybrid_score`를 최대 0.15 추가 부스트한다.

**Tech Stack:** Python 3.11, re (stdlib), pytest, JSONL files

## Global Constraints

- 모든 변경은 `main` 브랜치에서 직접 진행 (워크트리 없음)
- `infer_issue_score(text, utterance_type, position_type) -> float` — 반환값은 `round(float, 2)`, 범위 0.0–1.0
- `metadata["issue_score"]` — 청커가 저장, 키 이름 정확히 이 값
- `_ISSUE_SCORE_BOOST = 0.15` — retriever.py 모듈 수준 상수, 이름·값 고정
- `_apply_issue_boost(hits: list[dict], question_type: str | None = None) -> list[dict]` — retriever.py 모듈 수준 함수, 이름 고정
- 기존 테스트 전체 통과 유지 (`pytest tests/ -q`)
- 새 테스트는 기존 파일에 추가 (새 파일 생성 금지): `tests/test_question_types.py`, `tests/test_chunker_v2.py`, `tests/test_retriever_v2.py`
- 코드 주석 금지 (WHY가 자명한 경우)

---

## 파일 구조

| 역할 | 파일 | 작업 |
|---|---|---|
| 쟁점 점수 함수 | `service/rag/query/question_types.py` | 수정 (Task 1) |
| 청커 메타데이터 | `service/etl/transform/chunker_v2.py` | 수정 (Task 2) |
| 리트리버 부스트 | `service/rag/retrieval/retriever.py` | 수정 (Task 3) |
| 점수 함수 테스트 | `tests/test_question_types.py` | 수정 (Task 1) |
| 청커 테스트 | `tests/test_chunker_v2.py` | 수정 (Task 2) |
| 리트리버 테스트 | `tests/test_retriever_v2.py` | 수정 (Task 3) |
| Before/After 평가 | `eval/issue_extract_eval.py` | 신규 (Task 4) |

---

### Task 1: `infer_issue_score()` 쟁점 점수 함수

**Files:**
- Modify: `service/rag/query/question_types.py`
- Modify: `tests/test_question_types.py`

**Interfaces:**
- Consumes: 없음 (첫 번째 Task)
- Produces:
  - `_ISSUE_STRONG: re.Pattern` — 강한 쟁점 신호 (비리, 낭비, 쟁점 등)
  - `_ISSUE_MEDIUM: re.Pattern` — 중간 쟁점 신호 (문제가 있, 우려, 비판 등)
  - `_ISSUE_NUMERICAL: re.Pattern` — 수치형 고발 패턴 (XX억 낭비, XX건 위반 등)
  - `_ISSUE_DEMAND: re.Pattern` — 개선 요구 패턴 (시급히 개선, 즉각 조치 등)
  - `infer_issue_score(text: str, utterance_type: str = "", position_type: str = "") -> float`

**점수 산정 기준:**

| 신호 종류 | 조건 | 가산 |
|---|---|---|
| 강한 쟁점 단어 1개 | 쟁점·비리·낭비·위반 등 | +0.25 (최대 0.5) |
| 중간 쟁점 표현 1건 | 문제가 있, 우려, 비판 등 | +0.12 (최대 0.3) |
| 수치형 고발 | 3억 낭비, 10건 위반 | +0.20 |
| 개선 요구 | 시급히 개선, 즉각 조치 | +0.10 |
| 의원 질의 보너스 | utterance_type=="question" and position_type∈{"의원","위원장",""} | +0.10 |
| **최대** | | 1.00 |

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_question_types.py`에 다음을 추가한다:

```python
from service.rag.query.question_types import infer_issue_score


def test_issue_score_zero_for_neutral():
    assert infer_issue_score("오늘 회의를 개의하겠습니다. 감사합니다.") == 0.0


def test_issue_score_strong_signals():
    score = infer_issue_score("예산 낭비와 비리 쟁점이 심각합니다.")
    assert score >= 0.50


def test_issue_score_numerical_complaint():
    score = infer_issue_score("3억 원이 낭비되었습니다.")
    assert score >= 0.20


def test_issue_score_member_question_bonus():
    base = infer_issue_score("우려됩니다.", utterance_type="statement", position_type="정부측")
    boosted = infer_issue_score("우려됩니다.", utterance_type="question", position_type="의원")
    assert boosted > base


def test_issue_score_capped_at_one():
    text = "쟁점 논란 갈등 비리 낭비 위반 허점 부실 은폐 조작 허위 무책임"
    assert infer_issue_score(text) == 1.0


def test_issue_score_medium_signals():
    score = infer_issue_score("이 부분에 문제가 있습니다. 개선이 필요합니다.")
    assert 0.10 <= score <= 0.60
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_question_types.py::test_issue_score_zero_for_neutral \
                 tests/test_question_types.py::test_issue_score_strong_signals -v
```

Expected: FAIL (`infer_issue_score` 미존재)

- [ ] **Step 3: 4개 패턴 상수 + `infer_issue_score` 구현**

`question_types.py`에서 `_ISSUE_MARKERS` 정의(line ~123) 이후에 다음 4개 상수를 추가한다:

```python
_ISSUE_STRONG = re.compile(
    r"쟁점|논란|갈등|비리|낭비|위반|허점|부실|은폐|조작|허위|무책임|직무유기|실패|파탄"
)
_ISSUE_MEDIUM = re.compile(
    r"문제(?:가|점이|가\s*있|가\s*되)|우려(?:가|를|스럽)|비판(?:을|받|하)(?:고|며|여)?"
    r"|지적(?:을|하|되)|개선이\s*필요|시급(?:히|한)|즉각\s*(?:조치|대응|해결)"
)
_ISSUE_NUMERICAL = re.compile(
    r"\d+[억만천백십]\s*원?\s*(?:낭비|손실|초과|부족|횡령|유용|누락)"
    r"|\d+\s*(?:건|명)\s*(?:미처리|적발|위반|불법)"
)
_ISSUE_DEMAND = re.compile(
    r"(?:시급|즉각|반드시|당장|조속히)\s*(?:개선|조치|해결|대응|수정|폐지|도입|강화|점검)"
)
```

그리고 파일 끝 `embed_hint_labels` 함수 뒤에 다음 함수를 추가한다:

```python
def infer_issue_score(
    text: str, utterance_type: str = "", position_type: str = ""
) -> float:
    body = (text or "").strip()
    if not body:
        return 0.0
    score = 0.0
    strong_count = len(_ISSUE_STRONG.findall(body))
    score += min(strong_count * 0.25, 0.50)
    medium_count = len(_ISSUE_MEDIUM.findall(body))
    score += min(medium_count * 0.12, 0.30)
    if _ISSUE_NUMERICAL.search(body):
        score += 0.20
    if _ISSUE_DEMAND.search(body):
        score += 0.10
    if utterance_type == "question" and position_type in ("의원", "위원장", ""):
        score += 0.10
    return min(round(score, 2), 1.0)
```

- [ ] **Step 4: 전체 테스트 실행**

```bash
python -m pytest tests/test_question_types.py -v
```

Expected: 28개 통과 (기존 22개 + 새 6개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "feat: infer_issue_score — 쟁점 점수 함수 추가 (Algorithm #3)"
```

---

### Task 2: 청커에 `issue_score` 메타데이터 통합

**Files:**
- Modify: `service/etl/transform/chunker_v2.py`
- Modify: `tests/test_chunker_v2.py`

**Interfaces:**
- Consumes: Task 1의 `infer_issue_score(text, utterance_type, position_type) -> float`
- Produces: `metadata["issue_score"]: float` — `round(float, 2)` 형태로 저장

**현재 chunker_v2.py imports (line ~1–12):**
```python
from service.rag.query.question_types import (
    embed_hint_labels,
    infer_agency,
    infer_chunk_question_type_hints,
    infer_utterance_type,
    infer_utterance_type_with_confidence,
)
```

`infer_issue_score`를 이 import 목록에 추가한다.

**현재 `_enrich_question_type_metadata` (line ~92–105):**
```python
def _enrich_question_type_metadata(meta: dict, text: str, speaker: str, speaker_role: str) -> None:
    meta["agency"] = infer_agency(speaker_role, text)
    utype, confidence = infer_utterance_type_with_confidence(
        text,
        speaker_role=speaker_role,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["utterance_type"] = utype
    meta["utterance_type_confidence"] = round(confidence, 2)
    meta["question_type_hints"] = infer_chunk_question_type_hints(
        text,
        speaker=speaker,
        speaker_role=speaker_role,
        metadata=meta,
    )
```

`meta["utterance_type_confidence"]` 저장 직후에 `issue_score` 한 줄을 추가한다:

```python
    meta["utterance_type_confidence"] = round(confidence, 2)
    meta["issue_score"] = infer_issue_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_chunker_v2.py`에 다음을 추가한다:

```python
def test_build_record_has_issue_score():
    record = _build_record(
        _turn("예산 낭비와 비리가 쟁점입니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert "issue_score" in record["metadata"]
    score = record["metadata"]["issue_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_build_record_issue_score_high_for_issue_text():
    record = _build_record(
        _turn("예산 낭비와 비리 문제가 쟁점이 됩니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert record["metadata"]["issue_score"] >= 0.50
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_chunker_v2.py::test_build_record_has_issue_score -v
```

Expected: FAIL

- [ ] **Step 3: chunker_v2.py 수정**

`chunker_v2.py`의 import 목록에 `infer_issue_score`를 추가하고, `_enrich_question_type_metadata`에 `issue_score` 저장 라인을 추가한다 (위의 설명 참조).

전체 수정 후 `_enrich_question_type_metadata`는 다음과 같아야 한다:

```python
def _enrich_question_type_metadata(meta: dict, text: str, speaker: str, speaker_role: str) -> None:
    meta["agency"] = infer_agency(speaker_role, text)
    utype, confidence = infer_utterance_type_with_confidence(
        text,
        speaker_role=speaker_role,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["utterance_type"] = utype
    meta["utterance_type_confidence"] = round(confidence, 2)
    meta["issue_score"] = infer_issue_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["question_type_hints"] = infer_chunk_question_type_hints(
        text,
        speaker=speaker,
        speaker_role=speaker_role,
        metadata=meta,
    )
```

- [ ] **Step 4: 테스트 실행**

```bash
python -m pytest tests/test_chunker_v2.py -v
```

Expected: 14개 통과 (기존 12개 + 새 2개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/etl/transform/chunker_v2.py tests/test_chunker_v2.py
git commit -m "feat: issue_score chunker metadata에 저장"
```

---

### Task 3: 리트리버 issue-aware 부스트

**Files:**
- Modify: `service/rag/retrieval/retriever.py`
- Modify: `tests/test_retriever_v2.py`

**Interfaces:**
- Consumes: `metadata["issue_score"]` (Task 2에서 저장됨)
- Produces:
  - `_ISSUE_SCORE_BOOST: float = 0.15` — 모듈 수준 상수
  - `_apply_issue_boost(hits: list[dict], question_type: str | None = None) -> list[dict]` — 모듈 수준 함수

**`_apply_issue_boost` 로직:**
- `question_type != "issue_extract"` 이면 hits를 그대로 반환 (no-op)
- 해당하면 각 hit의 `hybrid_score += 0.15 * hit["metadata"]["issue_score"]`
- `hybrid_score` 내림차순으로 재정렬 후 반환

**retriever.py 수정 위치 1 — `search()` 메서드:**
현재 `out = self._dedupe_by_chunk_id(out)` 바로 다음(line ~173) 에 1줄 추가:
```python
out = self._dedupe_by_chunk_id(out)
out = _apply_issue_boost(out, question_type=question_type)  # NEW
```

**retriever.py 수정 위치 2 — `search_v2()` 메서드:**
현재 `for hit in merged: hit["hybrid_score"] = hit.get("rrf_score", 0.0)` 루프(line ~429) 다음에 1줄 추가:
```python
for hit in merged:
    hit["hybrid_score"] = hit.get("rrf_score", 0.0)
merged = _apply_issue_boost(merged, question_type=question_type)  # NEW
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_retriever_v2.py`에 다음을 추가한다 (파일 최하단):

```python
from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST


def test_apply_issue_boost_reorders_for_issue_extract():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"issue_score": 0.0}},
        {"hybrid_score": 0.70, "metadata": {"issue_score": 1.0}},
    ]
    result = _apply_issue_boost(hits, question_type="issue_extract")
    # 두 번째 hit: 0.70 + 0.15 * 1.0 = 0.85 > 0.80 → 첫 번째로 올라와야 함
    assert result[0]["metadata"]["issue_score"] == 1.0
    assert result[0]["hybrid_score"] == pytest.approx(0.85)


def test_apply_issue_boost_noop_for_other_types():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"issue_score": 0.0}},
        {"hybrid_score": 0.70, "metadata": {"issue_score": 1.0}},
    ]
    result = _apply_issue_boost(hits, question_type="topic_search")
    # 순서 변화 없어야 함
    assert result[0]["hybrid_score"] == 0.80
```

또한 파일 상단에 `import pytest`가 없으면 추가한다:
```python
import pytest
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_retriever_v2.py::test_apply_issue_boost_reorders_for_issue_extract -v
```

Expected: FAIL (`_apply_issue_boost` 미존재)

- [ ] **Step 3: retriever.py에 상수·함수·통합 코드 추가**

`retriever.py` 파일 최상단 imports 아래, `_rrf_merge` 함수 위에 다음을 추가한다:

```python
_ISSUE_SCORE_BOOST = 0.15


def _apply_issue_boost(
    hits: list[dict], question_type: str | None = None
) -> list[dict]:
    if (question_type or "").strip() != "issue_extract":
        return hits
    for hit in hits:
        issue_score = float((hit.get("metadata") or {}).get("issue_score", 0.0))
        hit["hybrid_score"] = float(hit.get("hybrid_score", 0.0)) + _ISSUE_SCORE_BOOST * issue_score
    return sorted(hits, key=lambda x: -float(x.get("hybrid_score", 0.0)))
```

그 다음 `search()` 메서드의 `_dedupe_by_chunk_id` 호출 직후에:
```python
        out = self._dedupe_by_chunk_id(out)
        out = _apply_issue_boost(out, question_type=question_type)
```

그 다음 `search_v2()` 메서드의 hybrid_score 설정 루프 직후에:
```python
        for hit in merged:
            hit["hybrid_score"] = hit.get("rrf_score", 0.0)
        merged = _apply_issue_boost(merged, question_type=question_type)
```

- [ ] **Step 4: 전체 테스트 실행**

```bash
python -m pytest tests/test_retriever_v2.py -v
```

Expected: 10개 통과 (기존 8개 + 새 2개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: issue_extract 검색 시 issue_score 부스트 (Algorithm #3)"
```

---

### Task 4: Before/After 평가 스크립트

**Files:**
- Create: `eval/issue_extract_eval.py`

**Interfaces:**
- Consumes:
  - `data/v2/transform/final/chunks_v2.jsonl` (utterance 청크, issue_score 포함)
  - Task 1–3의 `infer_issue_score`, `_apply_issue_boost`, `_ISSUE_SCORE_BOOST`
- Produces: stdout 리포트

**평가 로직:**
- JSONL에서 utterance 청크 로드
- 각 청크에 대해 새 `infer_issue_score()` 재계산
- 분포 출력: issue_score 구간별 청크 수 (0.0 / 0.01-0.24 / 0.25-0.49 / 0.50-0.74 / 0.75+)
- 상위 쟁점 청크 10건 미리보기 (score, speaker, 텍스트 앞 80자)
- 부스트 시뮬레이션: 랜덤 쿼리 5개에 대해 before/after 순위 변화 출력

- [ ] **Step 1: 스크립트 작성**

`eval/issue_extract_eval.py`를 아래 내용으로 작성한다:

```python
"""
핵심 쟁점 추출 알고리즘 Before/After 평가

사용법:
    python eval/issue_extract_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import infer_issue_score
from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST


def load_utterance_chunks() -> list[dict]:
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


def simulate_boost(chunks: list[dict], query_keywords: list[str], top_k: int = 8) -> tuple[list[dict], list[dict]]:
    filtered = [c for c in chunks if any(kw in (c.get("clean_text") or "") for kw in query_keywords)]
    if not filtered:
        return [], []
    for c in filtered:
        c["hybrid_score"] = float(len([kw for kw in query_keywords if kw in (c.get("clean_text") or "")])) / len(query_keywords)
    before = sorted(filtered, key=lambda x: -x.get("hybrid_score", 0.0))[:top_k]
    hits_for_boost = [{"hybrid_score": c["hybrid_score"], "metadata": c.get("metadata", {}), "clean_text": c.get("clean_text", ""), "speaker": c.get("speaker", "")} for c in filtered]
    after_hits = _apply_issue_boost(hits_for_boost, question_type="issue_extract")[:top_k]
    return before, after_hits


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    if not chunks:
        return
    print(f"utterance 청크: {len(chunks):,}개\n")

    scored = []
    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("clean_text", "")
        utype = meta.get("utterance_type", "statement")
        ptype = meta.get("position_type", "")
        score = infer_issue_score(text, utterance_type=utype, position_type=ptype)
        scored.append((score, c.get("speaker", ""), text))

    sep = "=" * 65
    thin = "-" * 65

    print(sep)
    print("  issue_score 분포")
    print(sep)
    buckets = Counter()
    for score, _, _ in scored:
        if score == 0.0:
            buckets["0.00 (없음)"] += 1
        elif score < 0.25:
            buckets["0.01–0.24 (미약)"] += 1
        elif score < 0.50:
            buckets["0.25–0.49 (보통)"] += 1
        elif score < 0.75:
            buckets["0.50–0.74 (강함)"] += 1
        else:
            buckets["0.75+ (매우 강함)"] += 1

    for label in ["0.00 (없음)", "0.01–0.24 (미약)", "0.25–0.49 (보통)", "0.50–0.74 (강함)", "0.75+ (매우 강함)"]:
        cnt = buckets.get(label, 0)
        pct = cnt / len(scored) * 100
        bar = "█" * min(30, int(pct / 2))
        print(f"  {label:<22} {cnt:>7,}개 ({pct:4.1f}%) {bar}")

    print(f"\n{sep}")
    print("  상위 10개 쟁점 청크")
    print(sep)
    top10 = sorted(scored, key=lambda x: -x[0])[:10]
    for score, speaker, text in top10:
        print(f"  [{score:.2f}] {speaker[:8]:<8} {text[:70]}...")

    print(f"\n{sep}")
    print(f"  부스트 시뮬레이션 (max boost: {_ISSUE_SCORE_BOOST} × issue_score)")
    print(sep)

    test_queries = [
        (["예산", "낭비"], "예산 낭비 쟁점"),
        (["비리", "위반"], "비리·위반 쟁점"),
        (["우려", "문제"], "우려·문제 발언"),
        (["대북제재", "완화"], "대북제재 완화"),
        (["방송", "독립"], "방송 독립 쟁점"),
    ]

    for keywords, label in test_queries:
        before, after = simulate_boost(chunks, keywords)
        if not before:
            print(f"\n  [{label}] 해당 청크 없음")
            continue
        b_avg_score = sum(float((x.get("metadata") or {}).get("issue_score", 0.0)) for x in [{"metadata": c.get("metadata", {})} for c in before]) / max(len(before), 1)
        a_avg_score = sum(float((x.get("metadata") or {}).get("issue_score", 0.0)) for x in after) / max(len(after), 1)
        print(f"\n  [{label}] top-{len(before)} avg issue_score: Before={b_avg_score:.2f} → After={a_avg_score:.2f}")

    print(sep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행**

```bash
python eval/issue_extract_eval.py
```

Expected: 리포트 정상 출력 (청크 파일 없으면 "청크 파일 없음" 메시지로 종료)

- [ ] **Step 3: 커밋**

```bash
git add eval/issue_extract_eval.py
git commit -m "eval: 핵심 쟁점 추출 before/after 평가 스크립트 추가"
```

---

## Self-Review

**Spec coverage 확인:**
- ✅ `infer_issue_score(text, utterance_type, position_type) -> float` — round 2자리, 0.0–1.0 (Task 1)
- ✅ 4개 패턴 상수: `_ISSUE_STRONG`, `_ISSUE_MEDIUM`, `_ISSUE_NUMERICAL`, `_ISSUE_DEMAND` (Task 1)
- ✅ `metadata["issue_score"]` 저장 (Task 2)
- ✅ `_ISSUE_SCORE_BOOST = 0.15` 모듈 수준 상수 (Task 3)
- ✅ `_apply_issue_boost(hits, question_type) -> list[dict]` 모듈 수준 함수 (Task 3)
- ✅ search() + search_v2() 양쪽 통합 (Task 3)
- ✅ 새 테스트는 기존 파일에만 추가 (Tasks 1, 2, 3)
- ✅ Before/after eval (Task 4)

**Placeholder scan:** 없음

**Type consistency:**
- `infer_issue_score` → `float` — Task 1 정의, Task 2 소비 일치
- `metadata["issue_score"]` 키 — Task 2 저장, Task 3 `_apply_issue_boost`에서 읽기 일치
- `_apply_issue_boost(hits: list[dict], question_type: str | None) -> list[dict]` — Task 3 정의, 테스트에서 직접 import 일치

**Import 일관성:**
- Task 2: chunker_v2.py가 `infer_issue_score`를 question_types.py에서 import — 정확히 명시됨
- Task 3: 테스트가 `from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST` — 정확히 명시됨
