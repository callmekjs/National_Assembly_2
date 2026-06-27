# Algorithm #4: 발언 중요도 점수화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 각 발화 청크에 `importance_score`(0.0–1.0)를 부여하고, `topic_search` 질문 유형 검색 시 고득점 청크가 컨텍스트 상위에 노출되어 LLM이 핵심 발언을 먼저 읽도록 한다.

**Architecture:** `question_types.py`에 `infer_importance_score()` 규칙 기반 함수를 추가해 정부 약속/계획 표현, 정책 결정 단어, 공식 발언 패턴을 점수화한다. `chunker_v2.py`가 `metadata["importance_score"]`에 저장한다. 리트리버(`retriever.py`)는 `topic_search` 질문 유형일 때 `_apply_importance_boost()`로 `hybrid_score`를 최대 0.10 부스트해 중요 발언을 상위에 배치한다.

**Tech Stack:** Python 3.11, re (stdlib), pytest, JSONL files

## Global Constraints

- 모든 변경은 `main` 브랜치에서 직접 진행 (워크트리 없음)
- `infer_importance_score(text, utterance_type, position_type) -> float` — 반환값은 `round(float, 2)`, 범위 0.0–1.0
- `metadata["importance_score"]` — 청커가 저장, 키 이름 정확히 이 값
- `_IMPORTANCE_BOOST = 0.10` — retriever.py 모듈 수준 상수, 이름·값 고정
- `_apply_importance_boost(hits: list[dict], question_type: str | None = None) -> list[dict]` — retriever.py 모듈 수준 함수, 이름 고정
- 기존 테스트 전체 통과 유지 (`pytest tests/ -q`)
- 새 테스트는 기존 파일에 추가 (새 파일 생성 금지): `tests/test_question_types.py`, `tests/test_chunker_v2.py`, `tests/test_retriever_v2.py`
- 코드 주석 금지 (WHY가 자명한 경우)

---

## 파일 구조

| 역할 | 파일 | 작업 |
|---|---|---|
| 중요도 점수 함수 | `service/rag/query/question_types.py` | 수정 (Task 1) |
| 청커 메타데이터 | `service/etl/transform/chunker_v2.py` | 수정 (Task 2) |
| 리트리버 부스트 | `service/rag/retrieval/retriever.py` | 수정 (Task 3) |
| 점수 함수 테스트 | `tests/test_question_types.py` | 수정 (Task 1) |
| 청커 테스트 | `tests/test_chunker_v2.py` | 수정 (Task 2) |
| 리트리버 테스트 | `tests/test_retriever_v2.py` | 수정 (Task 3) |
| Before/After 평가 | `eval/importance_eval.py` | 신규 (Task 4) |

---

### Task 1: `infer_importance_score()` 중요도 점수 함수

**Files:**
- Modify: `service/rag/query/question_types.py`
- Modify: `tests/test_question_types.py`

**Interfaces:**
- Consumes: 없음 (독립 Task)
- Produces:
  - `_IMPORTANCE_COMMITMENT: re.Pattern` — 정부 약속·계획 동사 (추진하겠습니다, 검토하겠습니다 등)
  - `_IMPORTANCE_DECISION: re.Pattern` — 정책 결정 단어 (정부 입장, 시행령, 예산안 등)
  - `_IMPORTANCE_FORMAL: re.Pattern` — 공식 발언 표현 (장관으로서, 공식적으로 등)
  - `infer_importance_score(text: str, utterance_type: str = "", position_type: str = "") -> float`

**점수 산정 기준:**

| 신호 종류 | 조건 | 가산 |
|---|---|---|
| 약속·계획 동사 1건 | 추진하겠습니다, 검토하겠습니다 등 | +0.15 (최대 0.45) |
| 정책 결정 마커 | 정부 입장, 시행령, 예산안 등 | +0.20 |
| 공식 발언 표현 | 장관으로서, 공식적으로 등 | +0.15 |
| 정부측 공식 답변 | utterance_type=="answer" and position_type=="정부측" | +0.20 |
| 의원 공식 질의 | utterance_type=="question" and position_type∈{"의원","위원장"} | +0.10 |
| **최대** | | 1.00 |

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_question_types.py`의 기존 import 줄을 다음으로 교체한다:

```python
from service.rag.query.question_types import classify_question, route_defaults, infer_utterance_type, infer_utterance_type_with_confidence, infer_issue_score, infer_importance_score
```

그리고 파일 맨 아래에 다음 6개 테스트를 추가한다:

```python
def test_importance_score_zero_for_procedural():
    assert infer_importance_score("오늘 회의를 개의하겠습니다.") == 0.0


def test_importance_score_commitment_signals():
    score = infer_importance_score("조속히 검토하겠습니다. 시행하겠습니다.")
    assert score >= 0.15


def test_importance_score_decision_marker():
    score = infer_importance_score("정부 입장을 말씀드리겠습니다.")
    assert score >= 0.20


def test_importance_score_govt_answer_bonus():
    base = infer_importance_score("노력하겠습니다.", utterance_type="statement", position_type="의원")
    boosted = infer_importance_score("노력하겠습니다.", utterance_type="answer", position_type="정부측")
    assert boosted > base


def test_importance_score_capped_at_one():
    text = "시행하겠습니다. 추진하겠습니다. 마련하겠습니다. 정부 입장을 밝힙니다. 장관으로서 공식적으로 답변드립니다."
    assert infer_importance_score(text, utterance_type="answer", position_type="정부측") == 1.0


def test_importance_score_member_question_bonus():
    base = infer_importance_score("정부 입장은?", utterance_type="statement", position_type="기타")
    boosted = infer_importance_score("정부 입장은?", utterance_type="question", position_type="의원")
    assert boosted > base
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_question_types.py::test_importance_score_zero_for_procedural \
                 tests/test_question_types.py::test_importance_score_commitment_signals -v
```

Expected: FAIL (`infer_importance_score` 미존재)

- [ ] **Step 3: 3개 패턴 상수 + `infer_importance_score` 구현**

`question_types.py`에서 `_ISSUE_DEMAND` 정의 이후, `_QUESTION_ENDINGS` 정의 이전에 다음 3개 상수를 추가한다 (line ~138):

```python
_IMPORTANCE_COMMITMENT = re.compile(
    r"(?:추진|검토|마련|시행|개선|강화|보완|제출|협의|협력|노력|지원|점검|조치|수립|도입)"
    r"\s*하겠습니다"
)
_IMPORTANCE_DECISION = re.compile(
    r"정부\s*(?:입장|방침|계획|정책|대책)"
    r"|공식\s*(?:발표|입장|확인|답변)"
    r"|법률?\s*(?:개정|제정|시행)|시행령|예산안"
    r"|최종\s*(?:결정|확정)|방침\s*(?:을|이)\s*(?:결정|확정|수립)"
)
_IMPORTANCE_FORMAL = re.compile(
    r"(?:장관|차관|위원장|청장|처장|원장)으로서"
    r"|부처\s*(?:입장|방침|계획)"
    r"|공식적으로|정식으로"
)
```

그리고 파일 맨 끝 `infer_issue_score` 함수 이후에 다음 함수를 추가한다:

```python
def infer_importance_score(
    text: str, utterance_type: str = "", position_type: str = ""
) -> float:
    body = (text or "").strip()
    if not body:
        return 0.0
    score = 0.0
    commitment_count = len(_IMPORTANCE_COMMITMENT.findall(body))
    score += min(commitment_count * 0.15, 0.45)
    if _IMPORTANCE_DECISION.search(body):
        score += 0.20
    if _IMPORTANCE_FORMAL.search(body):
        score += 0.15
    if utterance_type == "answer" and position_type == "정부측":
        score += 0.20
    if utterance_type == "question" and position_type in ("의원", "위원장"):
        score += 0.10
    return min(round(score, 2), 1.0)
```

- [ ] **Step 4: 테스트 실행 확인**

먼저 test_importance_score_capped_at_one 로직을 손으로 검증한다:

텍스트: "시행하겠습니다. 추진하겠습니다. 마련하겠습니다. 정부 입장을 밝힙니다. 장관으로서 공식적으로 답변드립니다."

- commitment: 시행, 추진, 마련 = 3건 × 0.15 = 0.45 (cap 0.45 그대로)
- decision: "정부 입장" 포함 → +0.20
- formal: "장관으로서" 포함 → +0.15
- govt answer bonus: utterance_type="answer", position_type="정부측" → +0.20
- 합계: 0.45 + 0.20 + 0.15 + 0.20 = 1.00 → min(round(1.00, 2), 1.0) = 1.0 ✓

```bash
python -m pytest tests/test_question_types.py -v
```

Expected: 34개 통과 (기존 28개 + 새 6개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "feat: infer_importance_score — 중요도 점수 함수 추가 (Algorithm #4)"
```

---

### Task 2: 청커에 `importance_score` 메타데이터 통합

**Files:**
- Modify: `service/etl/transform/chunker_v2.py`
- Modify: `tests/test_chunker_v2.py`

**Interfaces:**
- Consumes: Task 1의 `infer_importance_score(text, utterance_type, position_type) -> float`
- Produces: `metadata["importance_score"]: float` — `round(float, 2)` 형태로 저장

**현재 chunker_v2.py imports (line 6–12):**
```python
from service.rag.query.question_types import (
    embed_hint_labels,
    infer_agency,
    infer_chunk_question_type_hints,
    infer_issue_score,
    infer_utterance_type_with_confidence,
)
```

`infer_importance_score`를 이 import 목록에 추가한다.

**현재 `_enrich_question_type_metadata` (line ~93–113):**
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

`meta["issue_score"]` 저장 직후에 `importance_score` 한 줄을 추가한다:

```python
    meta["issue_score"] = infer_issue_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
    meta["importance_score"] = infer_importance_score(
        text,
        utterance_type=utype,
        position_type=str(meta.get("position_type") or ""),
    )
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_chunker_v2.py`에 다음을 추가한다:

```python
def test_build_record_has_importance_score():
    record = _build_record(
        _turn("검토하겠습니다. 추진하겠습니다.", speaker="홍길동", role="장관"),
        "20240717_52128_52128",
    )
    assert "importance_score" in record["metadata"]
    score = record["metadata"]["importance_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_build_record_importance_score_high_for_govt_answer():
    record = _build_record(
        _turn("시행하겠습니다. 추진하겠습니다.", speaker="홍길동", role="장관"),
        "20240717_52128_52128",
    )
    assert record["metadata"]["importance_score"] >= 0.30
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_chunker_v2.py::test_build_record_has_importance_score -v
```

Expected: FAIL

- [ ] **Step 3: chunker_v2.py 수정**

import 목록에 `infer_importance_score` 추가, `_enrich_question_type_metadata`에 importance_score 저장 라인 추가 (위 설명 참조).

최종 `_enrich_question_type_metadata`는 다음과 같아야 한다:

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
    meta["importance_score"] = infer_importance_score(
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

Expected: 18개 통과 (기존 16개 + 새 2개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/etl/transform/chunker_v2.py tests/test_chunker_v2.py
git commit -m "feat: importance_score chunker metadata에 저장"
```

---

### Task 3: 리트리버 importance-aware 부스트

**Files:**
- Modify: `service/rag/retrieval/retriever.py`
- Modify: `tests/test_retriever_v2.py`

**Interfaces:**
- Consumes: `metadata["importance_score"]` (Task 2에서 저장됨)
- Produces:
  - `_IMPORTANCE_BOOST: float = 0.10` — 모듈 수준 상수
  - `_apply_importance_boost(hits: list[dict], question_type: str | None = None) -> list[dict]` — 모듈 수준 함수

**`_apply_importance_boost` 로직:**
- `question_type != "topic_search"` 이면 hits를 그대로 반환 (no-op)
- 해당하면 각 hit의 `hybrid_score += 0.10 * hit["metadata"]["importance_score"]`
- `hybrid_score` 내림차순으로 재정렬 후 반환

**retriever.py 추가 위치 — `_ISSUE_SCORE_BOOST` 상수 직후 (line ~13) 에 추가:**

현재:
```python
_ISSUE_SCORE_BOOST = 0.15


def _apply_issue_boost(
    hits: list[dict], question_type: str | None = None
) -> list[dict]:
    ...
```

다음으로 교체:
```python
_ISSUE_SCORE_BOOST = 0.15
_IMPORTANCE_BOOST = 0.10


def _apply_issue_boost(
    hits: list[dict], question_type: str | None = None
) -> list[dict]:
    if (question_type or "").strip() != "issue_extract":
        return hits
    for hit in hits:
        issue_score = float((hit.get("metadata") or {}).get("issue_score", 0.0))
        hit["hybrid_score"] = float(hit.get("hybrid_score", 0.0)) + _ISSUE_SCORE_BOOST * issue_score
    return sorted(hits, key=lambda x: -float(x.get("hybrid_score", 0.0)))


def _apply_importance_boost(
    hits: list[dict], question_type: str | None = None
) -> list[dict]:
    if (question_type or "").strip() != "topic_search":
        return hits
    for hit in hits:
        importance_score = float((hit.get("metadata") or {}).get("importance_score", 0.0))
        hit["hybrid_score"] = float(hit.get("hybrid_score", 0.0)) + _IMPORTANCE_BOOST * importance_score
    return sorted(hits, key=lambda x: -float(x.get("hybrid_score", 0.0)))
```

**retriever.py 수정 위치 1 — `search()` 메서드 (line ~188):**
```python
        out = self._dedupe_by_chunk_id(out)
        out = _apply_issue_boost(out, question_type=question_type)
        out = _apply_importance_boost(out, question_type=question_type)  # NEW
```

**retriever.py 수정 위치 2 — `search_v2()` 메서드 (line ~446):**
```python
        merged = _apply_issue_boost(merged, question_type=question_type)
        merged = _apply_importance_boost(merged, question_type=question_type)  # NEW
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_retriever_v2.py` 파일 최하단에 다음을 추가한다 (기존 `from service.rag.retrieval.retriever import _apply_issue_boost, _ISSUE_SCORE_BOOST` import는 이미 있으므로 아래 줄만 추가):

```python
from service.rag.retrieval.retriever import _apply_importance_boost, _IMPORTANCE_BOOST


def test_apply_importance_boost_reorders_for_topic_search():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="topic_search")
    # 두 번째 hit: 0.72 + 0.10 * 1.0 = 0.82 > 0.80 → 첫 번째로 올라와야 함
    assert result[0]["metadata"]["importance_score"] == 1.0
    assert result[0]["hybrid_score"] == pytest.approx(0.82)


def test_apply_importance_boost_noop_for_issue_extract():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="issue_extract")
    assert result[0]["hybrid_score"] == 0.80
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_retriever_v2.py::test_apply_importance_boost_reorders_for_topic_search -v
```

Expected: FAIL (`_apply_importance_boost` 미존재)

- [ ] **Step 3: retriever.py에 상수·함수·통합 코드 추가**

위 설명에 따라 `_IMPORTANCE_BOOST` 상수 추가, `_apply_importance_boost` 함수 추가, `search()` / `search_v2()` 양쪽에 호출 1줄씩 추가.

- [ ] **Step 4: 전체 테스트 실행**

```bash
python -m pytest tests/test_retriever_v2.py -v
```

Expected: 12개 통과 (기존 10개 + 새 2개)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: topic_search 검색 시 importance_score 부스트 (Algorithm #4)"
```

---

### Task 4: Before/After 평가 스크립트

**Files:**
- Create: `eval/importance_eval.py`

**Interfaces:**
- Consumes:
  - `data/v2/transform/final/chunks_v2.jsonl` (utterance 청크)
  - Task 1–3의 `infer_importance_score`, `_apply_importance_boost`, `_IMPORTANCE_BOOST`
- Produces: stdout 리포트

**평가 로직:**
- JSONL에서 utterance 청크 로드
- 각 청크에 대해 `infer_importance_score()` 재계산
- 분포 출력: importance_score 구간별 청크 수 (0.0 / 0.01–0.19 / 0.20–0.44 / 0.45–0.74 / 0.75+)
- position_type별 평균 중요도 출력 (정부측 vs 의원 vs 기타)
- 부스트 시뮬레이션: 랜덤 쿼리 5개에 대해 before/after 순위 변화 출력

- [ ] **Step 1: 스크립트 작성**

`eval/importance_eval.py`를 아래 내용으로 작성한다:

```python
"""
발언 중요도 점수화 알고리즘 Before/After 평가

사용법:
    python eval/importance_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import infer_importance_score
from service.rag.retrieval.retriever import _apply_importance_boost, _IMPORTANCE_BOOST


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
    hits_for_boost = [
        {
            "hybrid_score": c["hybrid_score"],
            "metadata": c.get("metadata", {}),
            "clean_text": c.get("clean_text", ""),
            "speaker": c.get("speaker", ""),
        }
        for c in filtered
    ]
    after_hits = _apply_importance_boost(hits_for_boost, question_type="topic_search")[:top_k]
    return before, after_hits


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    if not chunks:
        return
    print(f"utterance 청크: {len(chunks):,}개\n")

    scored = []
    position_scores: dict[str, list[float]] = defaultdict(list)
    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("clean_text", "")
        utype = meta.get("utterance_type", "statement")
        ptype = meta.get("position_type", "기타")
        score = infer_importance_score(text, utterance_type=utype, position_type=ptype)
        scored.append((score, c.get("speaker", ""), text, ptype))
        position_scores[ptype].append(score)

    sep = "=" * 65

    print(sep)
    print("  importance_score 분포")
    print(sep)
    buckets = Counter()
    for score, _, _, _ in scored:
        if score == 0.0:
            buckets["0.00 (없음)"] += 1
        elif score < 0.20:
            buckets["0.01–0.19 (미약)"] += 1
        elif score < 0.45:
            buckets["0.20–0.44 (보통)"] += 1
        elif score < 0.75:
            buckets["0.45–0.74 (강함)"] += 1
        else:
            buckets["0.75+ (매우 강함)"] += 1

    for label in ["0.00 (없음)", "0.01–0.19 (미약)", "0.20–0.44 (보통)", "0.45–0.74 (강함)", "0.75+ (매우 강함)"]:
        cnt = buckets.get(label, 0)
        pct = cnt / len(scored) * 100
        bar = "█" * min(30, int(pct / 2))
        print(f"  {label:<22} {cnt:>7,}개 ({pct:4.1f}%) {bar}")

    print(f"\n{sep}")
    print("  position_type별 평균 중요도")
    print(sep)
    for ptype in ["정부측", "의원", "위원장", "후보자", "전문위원", "기타"]:
        scores = position_scores.get(ptype, [])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        bar = "█" * min(20, int(avg * 20))
        print(f"  {ptype:<8} n={len(scores):>6,}  avg={avg:.3f}  {bar}")

    print(f"\n{sep}")
    print("  상위 10개 중요도 청크")
    print(sep)
    top10 = sorted(scored, key=lambda x: -x[0])[:10]
    for score, speaker, text, ptype in top10:
        print(f"  [{score:.2f}] {ptype:<6} {speaker[:6]:<6} {text[:65]}...")

    print(f"\n{sep}")
    print(f"  부스트 시뮬레이션 (max boost: {_IMPORTANCE_BOOST} × importance_score)")
    print(sep)

    test_queries = [
        (["추진", "하겠습니다"], "정부 추진 약속"),
        (["정부", "입장"], "정부 입장 발언"),
        (["시행령", "예산안"], "정책 결정 발언"),
        (["재외국민", "보호"], "외교 현안 질의"),
        (["방송", "독립"], "방송 정책 논의"),
    ]

    for keywords, label in test_queries:
        before, after = simulate_boost(chunks, keywords)
        if not before:
            print(f"\n  [{label}] 해당 청크 없음")
            continue
        b_avg = sum(float((c.get("metadata") or {}).get("importance_score", 0.0)) for c in before) / max(len(before), 1)
        a_avg = sum(float((x.get("metadata") or {}).get("importance_score", 0.0)) for x in after) / max(len(after), 1)
        print(f"\n  [{label}] top-{len(before)} avg importance_score: Before={b_avg:.2f} → After={a_avg:.2f}")

    print(sep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행**

```bash
python eval/importance_eval.py
```

Expected: 리포트 정상 출력 (청크 파일 없으면 "청크 파일 없음" 메시지로 종료)

- [ ] **Step 3: 커밋**

```bash
git add eval/importance_eval.py
git commit -m "eval: 발언 중요도 before/after 평가 스크립트 추가"
```

---

## Self-Review

**Spec coverage 확인:**
- ✅ `infer_importance_score(text, utterance_type, position_type) -> float` — round 2자리, 0.0–1.0 (Task 1)
- ✅ 3개 패턴 상수: `_IMPORTANCE_COMMITMENT`, `_IMPORTANCE_DECISION`, `_IMPORTANCE_FORMAL` (Task 1)
- ✅ `metadata["importance_score"]` 저장 (Task 2)
- ✅ `_IMPORTANCE_BOOST = 0.10` 모듈 수준 상수 (Task 3)
- ✅ `_apply_importance_boost(hits, question_type) -> list[dict]` 모듈 수준 함수 (Task 3)
- ✅ search() + search_v2() 양쪽 통합 (Task 3)
- ✅ 새 테스트는 기존 파일에만 추가 (Tasks 1, 2, 3)
- ✅ Before/after eval (Task 4)

**Placeholder scan:** 없음

**Type consistency:**
- `infer_importance_score` → `float` — Task 1 정의, Task 2 소비 일치
- `metadata["importance_score"]` 키 — Task 2 저장, Task 3 `_apply_importance_boost`에서 읽기 일치
- `_apply_importance_boost(hits: list[dict], question_type: str | None) -> list[dict]` — Task 3 정의, 테스트에서 직접 import 일치

**점수 검증 (test_importance_score_capped_at_one):**
- 텍스트: "시행하겠습니다. 추진하겠습니다. 마련하겠습니다. 정부 입장을 밝힙니다. 장관으로서 공식적으로 답변드립니다."
- commitment: 시행, 추진, 마련 = 3건 × 0.15 = 0.45 (cap 도달)
- decision: "정부 입장" → +0.20
- formal: "장관으로서" → +0.15
- govt answer: utterance_type="answer", position_type="정부측" → +0.20
- 합계: 0.45 + 0.20 + 0.15 + 0.20 = 1.00 ✓

**점수 검증 (test_apply_importance_boost_reorders_for_topic_search):**
- hit[1]: 0.70 + 0.10 × 1.0 = 0.80, hit[0]: 0.80 + 0.10 × 0.0 = 0.80
- 두 hit 동점(0.80) → sorted는 stable하므로 원래 순서 유지 가능 → importance_score=0.0이 첫 번째로 올 수 있음
- 테스트를 더 명확하게 수정: hit[1]의 importance_score를 1.0 대신, 초기 score 차를 더 크게 만들어 역전을 보장

**수정된 Task 3 Step 1 테스트 (위 테스트의 동점 문제 수정):**

```python
def test_apply_importance_boost_reorders_for_topic_search():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.65, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="topic_search")
    # 두 번째 hit: 0.65 + 0.10 * 1.0 = 0.75 < 0.80 — 여전히 역전 안 됨
    # 역전 보장을 위해: hit[1].hybrid_score = 0.72 → 0.72 + 0.10 = 0.82 > 0.80
```

**재수정 (확실한 역전):**

```python
def test_apply_importance_boost_reorders_for_topic_search():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="topic_search")
    # 두 번째 hit: 0.72 + 0.10 * 1.0 = 0.82 > 0.80 → 첫 번째로 올라와야 함
    assert result[0]["metadata"]["importance_score"] == 1.0
    assert result[0]["hybrid_score"] == pytest.approx(0.82)


def test_apply_importance_boost_noop_for_issue_extract():
    hits = [
        {"hybrid_score": 0.80, "metadata": {"importance_score": 0.0}},
        {"hybrid_score": 0.72, "metadata": {"importance_score": 1.0}},
    ]
    result = _apply_importance_boost(hits, question_type="issue_extract")
    assert result[0]["hybrid_score"] == 0.80
```

**Task 3 Step 1의 테스트는 위의 재수정된 버전을 사용한다** (hybrid_score 0.72, pytest.approx(0.82)).
