# Algorithm #2: 발화유형 분류 정확도 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `infer_utterance_type()`의 오분류(촉구형 발언 → question 잘못 분류)를 수정하고, 신뢰도 점수를 추가해 QA 쌍 품질을 높인다.

**Architecture:** `question_types.py`에 `_DEMAND_ONLY_ENDINGS` + `_INFO_SEEKING_MARKERS` 두 패턴을 추가해 촉구형 발언이 `question`으로 잘못 분류되는 문제를 수정한다. 동시에 `infer_utterance_type_with_confidence()`를 새로 추가해 분류 신뢰도(0.0–1.0)를 계산하고, chunker는 `utterance_type_confidence`를 metadata에 저장한다. QA pairer는 신뢰도 0.5 미만인 question을 statement로 처리해 노이즈 쌍을 차단한다.

**Tech Stack:** Python 3.11, pytest, re (stdlib), JSONL files (data/v2/transform/)

## Global Constraints

- 모든 변경은 `main` 브랜치에서 직접 진행 (워크트리 없음)
- `infer_utterance_type(text, speaker_role, position_type) -> str` 시그니처는 유지 (하위호환)
- `utterance_type` 값은 반드시 `question | answer | statement | procedural` 중 하나
- `utterance_type_confidence`는 float, 소수점 2자리 반올림 (`round(..., 2)`)
- 기존 테스트 전체 통과 유지 (`pytest tests/ -q`)
- 새 테스트는 `tests/test_question_types.py`, `tests/test_chunker_v2.py`, `tests/test_qa_pairer_v2.py` 에 추가 (파일 분리 금지)
- 코드 주석 금지 (WHY가 자명한 경우)

---

## 파일 구조

| 역할 | 파일 | 작업 |
|---|---|---|
| 분류 로직 | `service/rag/query/question_types.py` | 수정 (Task 1, 2) |
| 청커 메타데이터 | `service/etl/transform/chunker_v2.py` | 수정 (Task 3) |
| QA 페어러 필터 | `service/etl/transform/qa_pairer_v2.py` | 수정 (Task 3) |
| 분류기 테스트 | `tests/test_question_types.py` | 수정 (Task 1, 2) |
| 청커 테스트 | `tests/test_chunker_v2.py` | 수정 (Task 3) |
| QA 페어러 테스트 | `tests/test_qa_pairer_v2.py` | 수정 (Task 3) |
| Before/After 평가 | `eval/utterance_type_eval.py` | 신규 (Task 4) |

---

### Task 1: 촉구형 발언 오분류 수정 (`infer_utterance_type`)

**Files:**
- Modify: `service/rag/query/question_types.py` (lines 120–133 패턴 구역, lines 227–257 `infer_utterance_type`)
- Modify: `tests/test_question_types.py`

**Interfaces:**
- Consumes: 없음 (첫 번째 Task)
- Produces:
  - `_DEMAND_ONLY_ENDINGS: re.Pattern` — 촉구형 종결 표현 패턴 (모듈 수준 상수)
  - `_INFO_SEEKING_MARKERS: re.Pattern` — 정보 요청형 질의 패턴 (모듈 수준 상수)
  - `infer_utterance_type(text, speaker_role, position_type) -> str` — 시그니처 유지, 로직 개선

**현재 문제 사례 (수정 전):**
```
"북한 인권 문제에 대해 정부가 보다 적극적인 대응에 나서주시기 부탁드립니다."
→ 현재: question  (부탁드립니다 ∈ _QUESTION_ENDINGS)
→ 목표: statement (촉구형 발언, 정보 요청 없음)

"이 사안에 대해 철저한 조사와 대책 마련을 요청드립니다."
→ 현재: question
→ 목표: statement
```

**유지해야 할 정상 케이스 (수정 후에도 question):**
```
"통일부는 북한 인권 문제에 대해 어떤 대책을 갖고 있습니까?"
→ 정보 요청형: 유지

"왜 그 결정을 하셨는지 설명해 주십시오."
→ 정보 요청형: 유지

"이 법안 처리를 강력히 촉구합니다. 장관은 어떻게 생각하십니까?"
→ 촉구 + 정보 요청 혼합: question 유지 (혼합 발화)
```

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_question_types.py`에 다음을 추가한다:

```python
from service.rag.query.question_types import infer_utterance_type


def test_demand_ending_without_info_seeking_is_statement():
    result = infer_utterance_type(
        "북한 인권 문제에 대해 정부가 보다 적극적인 대응에 나서주시기 부탁드립니다.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "statement"


def test_request_ending_without_info_seeking_is_statement():
    result = infer_utterance_type(
        "이 사안에 대해 철저한 조사와 대책 마련을 요청드립니다.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "statement"


def test_demand_plus_info_seeking_is_question():
    result = infer_utterance_type(
        "이 법안 처리를 촉구합니다. 장관은 어떻게 생각하십니까?",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_pure_info_seeking_remains_question():
    result = infer_utterance_type(
        "통일부는 북한 인권 문제에 대해 어떤 대책을 갖고 있습니까?",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_explanation_request_remains_question():
    result = infer_utterance_type(
        "왜 그 결정을 하셨는지 설명해 주십시오.",
        speaker_role="위원",
        position_type="의원",
    )
    assert result == "question"


def test_government_answer_unchanged():
    result = infer_utterance_type(
        "답변드리겠습니다. 해당 사안은 검토 후 조치하겠습니다.",
        speaker_role="통일부장관",
        position_type="정부측",
    )
    assert result == "answer"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_question_types.py::test_demand_ending_without_info_seeking_is_statement \
                 tests/test_question_types.py::test_request_ending_without_info_seeking_is_statement -v
```

Expected: FAIL (현재 두 케이스 모두 "question"을 반환하므로)

- [ ] **Step 3: `question_types.py` 패턴 추가**

`_QUESTION_ENDINGS` 정의 직후(line 133 아래)에 두 상수를 추가한다:

```python
# 정보 요청 없이 요구/촉구만 있는 종결 표현 — 의원 발언에서 statement로 분류
_DEMAND_ONLY_ENDINGS = re.compile(
    r"(부탁드립니다|부탁합니다|요청합니다|요청드립니다"
    r"|촉구합니다|촉구드립니다|당부드립니다|당부합니다)"
    r"[\.\s]*$"
)

# 명확한 정보 요청 마커 — 이 패턴이 있으면 demand ending도 question으로 유지
_INFO_SEEKING_MARKERS = re.compile(
    r"어떻게\s*(?:보|생각|할|됩|되는|하실|하십)"
    r"|어떠합니까|어떻습니까|어떤\s*(?:입장|계획|방침|대책|생각)"
    r"|언제|얼마나?|몇\s*[번회개월년]"
    r"|왜\s|왜[,\?？]|왜$"
    r"|무엇|무슨"
    r"|(?:입|됩|않|없|십)니까"
    r"|설명해\s*주십시오|알려주십시오|답해\s*주십시오"
    r"|\?|？"
)
```

- [ ] **Step 4: `infer_utterance_type` 로직 수정**

`infer_utterance_type` 함수 내 의원 발언 분류 부분(line 248 이후)을 아래로 교체한다:

```python
    # ── 의원 발언 ──────────────────────────────────────────────
    # 1. 발언 마무리·의사진행 표현이 시작에 있으면 procedural
    if _MEMBER_PROCEDURAL.search(body[:60]):
        return "procedural"

    tail = body[-400:] if len(body) > 400 else body

    # 2. 촉구형 종결 + 정보 요청 없음 → statement (오분류 방지)
    if _DEMAND_ONLY_ENDINGS.search(tail) and not _INFO_SEEKING_MARKERS.search(body):
        return "statement"

    # 3. 발언 끝부분에 질의 종결 어미가 있으면 question
    if _QUESTION_ENDINGS.search(tail):
        return "question"

    # 4. 본문 어딘가에 기존 질의 마커가 있으면 question (fallback)
    if _QUESTION_MARKERS.search(body):
        return "question"

    return "statement"
```

- [ ] **Step 5: 전체 테스트 실행**

```bash
python -m pytest tests/test_question_types.py -v
```

Expected: 모든 테스트 통과 (기존 10개 + 새 6개 = 16개)

- [ ] **Step 6: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 기존 전체 테스트 모두 통과

- [ ] **Step 7: 커밋**

```bash
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "fix: 촉구형 발언 question 오분류 수정 — demand/info-seeking 패턴 분리"
```

---

### Task 2: 분류 신뢰도 함수 추가 (`infer_utterance_type_with_confidence`)

**Files:**
- Modify: `service/rag/query/question_types.py`
- Modify: `tests/test_question_types.py`

**Interfaces:**
- Consumes: Task 1의 `_DEMAND_ONLY_ENDINGS`, `_INFO_SEEKING_MARKERS`, `_QUESTION_ENDINGS`, `_QUESTION_MARKERS`, `_ANSWER_MARKERS`, `_PROCEDURAL_MARKERS`, `_MEMBER_PROCEDURAL`
- Produces:
  - `infer_utterance_type_with_confidence(text: str, speaker_role: str = "", position_type: str = "") -> tuple[str, float]`

**신뢰도 기준:**

| 케이스 | type | confidence |
|---|---|---|
| 위원장 + 의사진행 마커 | procedural | 0.95 |
| 정부측 + answer 마커 ("답변드리겠습니다") | answer | 0.92 |
| 정부측 + 마커 없음 | answer | 0.75 |
| 정부측 + question 마커 (반문) | statement | 0.70 |
| 의원 마무리 표현 (procedural) | procedural | 0.90 |
| 의원 + 촉구형 종결 + 정보요청 없음 | statement | 0.85 |
| 의원 + 명확 question ending + info-seeking | question | 0.90 |
| 의원 + question ending만 (info-seeking 없음) | question | 0.72 |
| 의원 + question markers 폴백 | question | 0.55 |
| 기타 statement | statement | 0.78 |

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_question_types.py`에 추가한다:

```python
from service.rag.query.question_types import infer_utterance_type_with_confidence


def test_confidence_clear_question_high():
    utype, conf = infer_utterance_type_with_confidence(
        "어떤 대책을 갖고 있습니까?", speaker_role="위원", position_type="의원"
    )
    assert utype == "question"
    assert conf >= 0.85


def test_confidence_demand_statement_high():
    utype, conf = infer_utterance_type_with_confidence(
        "철저한 조사를 부탁드립니다.", speaker_role="위원", position_type="의원"
    )
    assert utype == "statement"
    assert conf >= 0.80


def test_confidence_government_with_answer_marker_high():
    utype, conf = infer_utterance_type_with_confidence(
        "답변드리겠습니다. 검토 후 제출하겠습니다.",
        speaker_role="통일부장관", position_type="정부측"
    )
    assert utype == "answer"
    assert conf >= 0.88


def test_confidence_government_no_marker_medium():
    utype, conf = infer_utterance_type_with_confidence(
        "해당 정책은 지속적으로 추진하겠습니다.",
        speaker_role="외교부장관", position_type="정부측"
    )
    assert utype == "answer"
    assert 0.65 <= conf < 0.90


def test_confidence_fallback_question_low():
    utype, conf = infer_utterance_type_with_confidence(
        "이 부분이 어떻게 됩니까는 알고 싶은데요.",
        speaker_role="위원", position_type="의원"
    )
    assert utype == "question"
    assert conf < 0.80


def test_infer_utterance_type_backward_compat():
    # 기존 infer_utterance_type은 그대로 str 반환
    from service.rag.query.question_types import infer_utterance_type
    result = infer_utterance_type(
        "어떤 대책을 갖고 있습니까?", speaker_role="위원", position_type="의원"
    )
    assert isinstance(result, str)
    assert result == "question"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_question_types.py::test_confidence_clear_question_high \
                 tests/test_question_types.py::test_confidence_demand_statement_high -v
```

Expected: FAIL (`infer_utterance_type_with_confidence` 미존재)

- [ ] **Step 3: `infer_utterance_type_with_confidence` 구현**

`question_types.py`의 기존 `infer_utterance_type` 함수(line 227)를 아래 두 함수로 교체한다:

```python
def infer_utterance_type_with_confidence(
    text: str, speaker_role: str = "", position_type: str = ""
) -> tuple[str, float]:
    """발화유형과 분류 신뢰도(0.0–1.0)를 반환한다."""
    body = (text or "").strip()
    role = speaker_role or ""

    if "위원장" in role and _PROCEDURAL_MARKERS.search(body[:200]):
        return "procedural", 0.95

    if position_type in {"정부측", "후보자"} or is_government_role(role):
        has_q = bool(_QUESTION_MARKERS.search(body))
        has_a = bool(_ANSWER_MARKERS.search(body))
        if has_q and not has_a:
            return "statement", 0.70
        confidence = 0.92 if has_a else 0.75
        return "answer", confidence

    if _MEMBER_PROCEDURAL.search(body[:60]):
        return "procedural", 0.90

    tail = body[-400:] if len(body) > 400 else body

    if _DEMAND_ONLY_ENDINGS.search(tail):
        has_info = bool(_INFO_SEEKING_MARKERS.search(body))
        if not has_info:
            return "statement", 0.85
        return "question", 0.72

    if _QUESTION_ENDINGS.search(tail):
        has_info = bool(_INFO_SEEKING_MARKERS.search(body))
        confidence = 0.90 if has_info else 0.72
        return "question", confidence

    if _QUESTION_MARKERS.search(body):
        return "question", 0.55

    return "statement", 0.78


def infer_utterance_type(text: str, speaker_role: str = "", position_type: str = "") -> str:
    utype, _ = infer_utterance_type_with_confidence(text, speaker_role, position_type)
    return utype
```

- [ ] **Step 4: 전체 테스트 실행**

```bash
python -m pytest tests/test_question_types.py -v
```

Expected: 22개 테스트 모두 통과 (기존 10 + Task 1 추가 6 + Task 2 추가 6)

- [ ] **Step 5: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add service/rag/query/question_types.py tests/test_question_types.py
git commit -m "feat: 발화유형 신뢰도 점수 함수 추가 — infer_utterance_type_with_confidence"
```

---

### Task 3: chunker + QA pairer에 신뢰도 통합

**Files:**
- Modify: `service/etl/transform/chunker_v2.py` (line 92–105 `_enrich_question_type_metadata`)
- Modify: `service/etl/transform/qa_pairer_v2.py` (line 162–163 utterance_type 읽는 부분)
- Modify: `tests/test_chunker_v2.py`
- Modify: `tests/test_qa_pairer_v2.py`

**Interfaces:**
- Consumes: Task 2의 `infer_utterance_type_with_confidence(text, speaker_role, position_type) -> tuple[str, float]`
- Produces:
  - chunker: metadata에 `utterance_type_confidence: float` 필드 추가
  - QA pairer: `utterance_type_confidence < 0.5`인 question은 statement로 처리

**QA pairer 신뢰도 필터 임계값:** `CONFIDENCE_THRESHOLD = 0.5` (모듈 수준 상수)

**QA pairer 기존 코드 (line 162–163):**
```python
        utterance_type = chunk.get("metadata", {}).get("utterance_type", "statement")
        gap = _gap(prev_chunk, chunk)
```

**QA pairer 변경 후:**
```python
        meta = chunk.get("metadata", {})
        utterance_type = meta.get("utterance_type", "statement")
        confidence = float(meta.get("utterance_type_confidence", 1.0))
        if utterance_type == "question" and confidence < CONFIDENCE_THRESHOLD:
            utterance_type = "statement"
        gap = _gap(prev_chunk, chunk)
```

- [ ] **Step 1: chunker 테스트 추가**

`tests/test_chunker_v2.py`에 추가한다:

```python
def test_build_record_has_utterance_type_confidence():
    record = _build_record(
        _turn("어떤 대책을 갖고 있습니까?", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    assert "utterance_type_confidence" in record["metadata"]
    conf = record["metadata"]["utterance_type_confidence"]
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0


def test_demand_statement_has_high_confidence():
    record = _build_record(
        _turn("철저한 대책 마련을 부탁드립니다.", speaker="이재정", role="위원"),
        "20240717_52128_52128",
    )
    meta = record["metadata"]
    assert meta["utterance_type"] == "statement"
    assert meta["utterance_type_confidence"] >= 0.80
```

- [ ] **Step 2: QA pairer 테스트 추가**

`tests/test_qa_pairer_v2.py`에 다음을 추가한다:

```python
def test_low_confidence_question_excluded_from_pairs():
    """confidence < 0.5인 question은 statement 처리되어 QA 쌍 미생성."""
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원",
              "잘 부탁드립니다."),
        _turn("SRC1", 1, "answer", "조태열", "장관", "정부측",
              "답변드리겠습니다."),
    ]
    # confidence 0.3 주입
    turns[0]["metadata"]["utterance_type_confidence"] = 0.3
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 0


def test_high_confidence_question_included_in_pairs():
    """confidence >= 0.5인 question은 정상 QA 쌍 생성."""
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원",
              "어떤 대책을 갖고 있습니까?"),
        _turn("SRC1", 1, "answer", "조태열", "장관", "정부측",
              "검토 후 조치하겠습니다."),
    ]
    turns[0]["metadata"]["utterance_type_confidence"] = 0.90
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1


def test_missing_confidence_defaults_to_include():
    """utterance_type_confidence 필드 없으면 기본값 1.0 → 정상 포함."""
    turns = [
        _turn("SRC1", 0, "question", "이재정", "위원", "의원",
              "어떤 대책을 갖고 있습니까?"),
        _turn("SRC1", 1, "answer", "조태열", "장관", "정부측",
              "검토 후 조치하겠습니다."),
    ]
    # confidence 필드 없음 (기존 데이터 호환)
    assert "utterance_type_confidence" not in turns[0]["metadata"]
    pairs = pair_qa_chunks(turns)
    assert len(pairs) == 1
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
python -m pytest tests/test_chunker_v2.py::test_build_record_has_utterance_type_confidence \
                 tests/test_qa_pairer_v2.py::test_low_confidence_question_excluded_from_pairs -v
```

Expected: FAIL

- [ ] **Step 4: chunker 수정**

`chunker_v2.py`의 `_enrich_question_type_metadata` 함수(line 92–105)에서 import를 추가하고 confidence를 저장한다:

```python
from service.rag.query.question_types import (
    embed_hint_labels,
    infer_agency,
    infer_chunk_question_type_hints,
    infer_utterance_type,
    infer_utterance_type_with_confidence,
)
```

그리고 `_enrich_question_type_metadata` 내부를:

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

(기존의 `meta["utterance_type"] = infer_utterance_type(...)` 줄을 위의 3줄로 교체)

- [ ] **Step 5: qa_pairer_v2.py 수정**

`qa_pairer_v2.py` 파일 상단에 상수 추가:

```python
CONFIDENCE_THRESHOLD = 0.5  # 이 미만인 question은 statement로 처리
```

그리고 `_pair_single_source` 함수 내 turn 처리 루프에서 (line 162 부근) 다음으로 교체:

```python
        meta = chunk.get("metadata", {})
        utterance_type = meta.get("utterance_type", "statement")
        confidence = float(meta.get("utterance_type_confidence", 1.0))
        if utterance_type == "question" and confidence < CONFIDENCE_THRESHOLD:
            utterance_type = "statement"
        gap = _gap(prev_chunk, chunk)
```

- [ ] **Step 6: 전체 테스트 실행**

```bash
python -m pytest tests/test_chunker_v2.py tests/test_qa_pairer_v2.py -v
```

Expected: 모두 통과 (chunker 기존 + 새 2개, qa_pairer 기존 + 새 3개)

- [ ] **Step 7: 회귀 테스트**

```bash
python -m pytest tests/ -q
```

Expected: 전체 통과

- [ ] **Step 8: 커밋**

```bash
git add service/etl/transform/chunker_v2.py service/etl/transform/qa_pairer_v2.py \
        tests/test_chunker_v2.py tests/test_qa_pairer_v2.py
git commit -m "feat: utterance_type_confidence chunker 저장 + QA pairer 신뢰도 필터"
```

---

### Task 4: Before/After 평가 스크립트

**Files:**
- Create: `eval/utterance_type_eval.py`

**Interfaces:**
- Consumes:
  - `data/v2/transform/final/chunks_v2.jsonl` (utterance 청크)
  - `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl` (기존 QA 쌍)
  - Task 1·2의 개선된 `infer_utterance_type`, `infer_utterance_type_with_confidence`
- Produces: stdout 리포트 (before/after 분포 비교)

**평가 로직:**
- JSONL에서 utterance 청크 로드
- 각 청크에 대해:
  - old_type: `metadata["utterance_type"]` (저장된 값)
  - new_type, new_conf: `infer_utterance_type_with_confidence(clean_text, speaker_role, position_type)` 재계산
- 변경된 케이스 집계:
  - `question → statement` 변경 수 (오분류 수정)
  - `statement → question` 변경 수 (누락 복구, 이 방향은 거의 없을 것)
- confidence 분포 (구간별 비율)
- QA 쌍 영향 추정:
  - `question` 청크 중 confidence < 0.5 비율 → "필터 제외 예상 쌍 수"

- [ ] **Step 1: 스크립트 작성**

`eval/utterance_type_eval.py`를 아래 내용으로 작성한다:

```python
"""
발화유형 분류 정확도 개선 Before/After 평가

사용법:
    python eval/utterance_type_eval.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

from service.rag.query.question_types import infer_utterance_type_with_confidence


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


def main() -> None:
    print("데이터 로딩 중...", flush=True)
    chunks = load_utterance_chunks()
    print(f"utterance 청크: {len(chunks):,}개\n")

    old_dist: Counter = Counter()
    new_dist: Counter = Counter()
    changed: list[dict] = []
    conf_buckets: Counter = Counter()
    low_conf_questions = 0

    for c in chunks:
        meta = c.get("metadata", {})
        old_type = meta.get("utterance_type", "statement")
        speaker_role = c.get("speaker_role", "")
        position_type = str(meta.get("position_type") or "")
        text = c.get("clean_text", "")

        new_type, conf = infer_utterance_type_with_confidence(text, speaker_role, position_type)

        old_dist[old_type] += 1
        new_dist[new_type] += 1

        if new_type != old_type:
            changed.append({
                "chunk_id": c.get("chunk_id", ""),
                "old": old_type,
                "new": new_type,
                "conf": conf,
                "text_preview": text[:80],
            })

        bucket = f"{int(conf * 10) * 10}-{int(conf * 10) * 10 + 10}%"
        conf_buckets[bucket] += 1

        if new_type == "question" and conf < 0.5:
            low_conf_questions += 1

    sep = "=" * 65
    thin = "-" * 65

    print(sep)
    print("  발화유형 분류 Before / After 비교")
    print(sep)

    print(f"\n{'유형':<12} {'Before':>10} {'After':>10} {'변화':>10}")
    print(thin)
    for utype in ["question", "answer", "statement", "procedural"]:
        b = old_dist.get(utype, 0)
        a = new_dist.get(utype, 0)
        delta = a - b
        delta_str = f"+{delta:,}" if delta > 0 else (f"{delta:,}" if delta < 0 else "—")
        print(f"{utype:<12} {b:>10,} {a:>10,} {delta_str:>10}")
    print(thin)
    print(f"{'합계':<12} {sum(old_dist.values()):>10,} {sum(new_dist.values()):>10,}")

    print(f"\n{sep}")
    print("  변경 케이스 분석")
    print(sep)
    change_types: Counter = Counter()
    for item in changed:
        change_types[f"{item['old']} → {item['new']}"] += 1
    for change_label, cnt in change_types.most_common():
        print(f"  {change_label:<25} {cnt:>6,}건")

    if changed:
        print(f"\n  상위 10개 변경 예시 (question → statement):")
        examples = [c for c in changed if c["old"] == "question" and c["new"] == "statement"][:10]
        for ex in examples:
            print(f"  [{ex['conf']:.2f}] {ex['text_preview']}...")

    print(f"\n{sep}")
    print("  신뢰도 분포 (새 분류 기준)")
    print(sep)
    for bucket in sorted(conf_buckets.keys()):
        cnt = conf_buckets[bucket]
        bar = "█" * min(40, cnt // max(1, len(chunks) // 400))
        print(f"  {bucket:<10} {cnt:>7,}개  {bar}")

    print(f"\n{sep}")
    print("  QA 쌍 영향 추정 (confidence < 0.5 필터 기준)")
    print(sep)
    new_questions = new_dist.get("question", 0)
    print(f"  새 question 청크 수:            {new_questions:>7,}개")
    print(f"  confidence < 0.5 제외 예상:     {low_conf_questions:>7,}개")
    remaining = new_questions - low_conf_questions
    print(f"  QA pairing 대상 question:       {remaining:>7,}개")
    if new_questions:
        print(f"  필터율:                         {low_conf_questions/new_questions*100:>7.1f}%")

    print(sep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행 테스트**

```bash
python eval/utterance_type_eval.py
```

Expected: 리포트 정상 출력 (청크 파일 없으면 "청크 파일 없음" 메시지)

- [ ] **Step 3: 커밋**

```bash
git add eval/utterance_type_eval.py
git commit -m "eval: 발화유형 분류 before/after 평가 스크립트 추가"
```

---

## Self-Review

**Spec coverage 확인:**
- ✅ `infer_utterance_type` 시그니처 유지 (Task 1, 2)
- ✅ 촉구형 발언 → statement 수정 (Task 1)
- ✅ `infer_utterance_type_with_confidence` 신규 함수 (Task 2)
- ✅ `utterance_type_confidence` metadata 저장 (Task 3 chunker)
- ✅ QA pairer confidence 필터 (Task 3)
- ✅ `CONFIDENCE_THRESHOLD = 0.5` 상수화 (Task 3)
- ✅ Before/after 평가 (Task 4)

**Placeholder scan:** 없음

**Type consistency:**
- `infer_utterance_type_with_confidence` → `tuple[str, float]` — Task 2 정의, Task 3 소비 일치
- `CONFIDENCE_THRESHOLD` → Task 3에서 정의 및 사용 일치
- `utterance_type_confidence` 키 이름 — Task 3 chunker 저장, Task 3 qa_pairer 읽기 일치

**Import 일관성:**
- Task 3에서 chunker의 import 목록에 `infer_utterance_type_with_confidence` 추가 명시됨
- `infer_utterance_type` 단독 import는 더 이상 필요 없으나 제거하면 기존 테스트 영향 가능 → **유지**

