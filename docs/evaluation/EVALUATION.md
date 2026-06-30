# Evaluation

성능이 좋다는 **근거·재현 방법**을 정리합니다. 상세 실험 로그는 [docs/dev-log/](docs/dev-log/)를 참고하세요.

---

## 핵심 지표 요약

<!-- EVAL_AUTO_START -->

> 🤖 자동 갱신: 2026-06-22 12:24 | 파일: `eval_report_day11.json`


### 최신 검색 회귀

| score% | recall@3 | mrr@3 | 통과 |
|--------|----------|-------|------|
| **100.0** | **100.0** | **0.9** | 10/10 |

| 유형 | score% | recall@3 | mrr@3 |
|------|--------|----------|-------|
| classification | 100.0 | 100.0 | 1.0 |
| comparative | 100.0 | 100.0 | 0.5 |
| summary | 100.0 | 100.0 | 1.0 |

### 최신 데이터 품질 (`quality_20260621_083553.json`)

| 항목 | 값 |
|------|----|
| 청크 수 | 18048 |
| 평균 청크 길이 | 287자 |
| speaker 채움률 | 98.6% |
| committee·date | 100.0% / 100.0% |

<!-- EVAL_AUTO_END -->

### 검색 회귀 (고정 eval, 10문항)

| 시점 | score% | recall@3 | mrr@3 | 비고 |
|------|--------|----------|-------|------|
| Day 2 기준선 (2026-05-07) | 60 | 20 | 0.200 | 4문항 FAIL |
| Day 6 튜닝 후 | 90 | 80 | 0.667 | candidate_multiplier·키워드 가점 |
| Day 7 | 90 | 80 | 0.667 | 유형별 집계 추가 |
| **Day 11 (2026-05-09)** | **100** | **100** | **0.900** | 10/10 PASS |
| 청킹 18k 재적재 후 (2026-06-21) | 100 | 100 | 0.900 | 유지 (문서 기록) |

스냅샷 파일: [`service/rag/eval_report_day11.json`](service/rag/eval_report_day11.json)

Day 7 스냅샷: [`service/rag/eval_report_day7.json`](service/rag/eval_report_day7.json)

### 유형별 (Day 11)

| 유형 | score% | recall@3 | mrr@3 |
|------|--------|----------|-------|
| classification | 100 | 100 | 1.0 |
| comparative | 100 | 100 | 0.5 |
| summary | 100 | 100 | 1.0 |

### 데이터 품질 (2026-06-21, 청킹 개선 후)

| 항목 | 값 |
|------|-----|
| 문서 수 | 55 (외교통일위원회) |
| 청크 수 | 18,048 |
| embeddings_e5 | 18,048 (정합) |
| speaker 채움률 | 98.6% |
| committee·date | 100% |
| 평균 청크 길이 | 287자 (p50=191) |

---

## 평가 데이터셋

| 파일 | 문항 수 | 용도 |
|------|---------|------|
| [`service/rag/eval_queries_fixed.json`](service/rag/eval_queries_fixed.json) | 10 | 회귀 기본 (라벨 source 5건) |
| [`service/rag/eval/eval_dataset.json`](service/rag/eval/eval_dataset.json) | 50 | 확장 eval + ground_truth 15건 |

질문 유형: `comparative` / `classification` / `summary`

---

## 재현 명령

환경: `PG_PORT=5433` (Docker `SKN18-3rd`), `.env`에 DB·OpenAI 키 설정.

### 1) 검색 회귀 (메인)

```powershell
python -m service.rag.evaluate_retrieval --pg-port 5433
```

리포트 저장:

```powershell
python -m service.rag.evaluate_retrieval --pg-port 5433 --report-out service/rag/eval_report_latest.json
```

### 2) 검색 인용 정합

```powershell
python -m service.rag.verify_streamlit_citation_alignment --pg-port 5433
```

### 3) RAGAS (LLM 답변 품질)

```powershell
python -m service.rag.eval.ragas_eval --limit 10
```

지표: faithfulness, answer_relevancy, context_precision, context_recall  
리포트: `data/reports/ragas_YYYYMMDD_HHMMSS.json`

### 4) A/B 검색 전략 비교

```powershell
python -m service.rag.eval.ab_compare --limit 10
```

전략: baseline / score_norm / multi_query / fusion / HyDE / neural_reranker / MMR / 앙상블

### 5) Day 13 스모크 (적재 정합)

```powershell
python -m service.rag.smoke_day13 --pg-port 5433
```

### 6) QA 데모 (수동)

```powershell
python -m service.rag.qa_demo --query "대북정책 핵심 쟁점을 요약해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --pg-port 5433
```

---

## 개선 궤적 (요약)

```text
Day 2:  recall@3 20%  — 후보 풀 부족, 도메인 키워드 미반영
Day 6:  recall@3 80%  — candidate_multiplier, 쿼리 확장, 키워드 가점
Day 11: recall@3 100% — 난항 질의(정보 공유 제한, 통일부 장관) 규칙·후보 배수
2026-06-21: 청킹 18k + 고급 검색 옵션 추가 (기본 UI는 opt-in)
```

---

## Grounding 품질 지표 (2026-06-22 강화)

`graph/nodes/grounding_check.py` — 문장 단위 인용 비율로 답변 근거 수준 측정.

### 측정 방식

```
grounding_score = 인용 있는 줄 수 / 의미 있는 줄 수
의미 있는 줄 = 길이 > 10자, 헤더/인용/마커 줄 제외
```

### 수준 정의

| 레벨 | 조건 | 동작 |
|------|------|------|
| FULL | score > 0.5 | 경고 없음 |
| PARTIAL | 0 < score ≤ 0.5 | `ℹ 일부 문장에 인용 번호 없음` 안내 삽입 |
| NONE | score = 0 | `⚠ 회의록에서 인용 번호 확인 불가` 경고 삽입 |

> 스트리밍 경로(LangGraph Generate 스킵)에서는 `pages/views/chat.py`의 `_handle_user_input()`이 동일 조건을 사후 체크해 경고 추가.

### 추가 검증 (2026-06-22 강화)

| 기능 | 검증 방법 |
|------|-----------|
| [n] 범위 검증 | `[7]` 같은 존재하지 않는 번호 → `[?]`로 교체됨을 확인 |
| 미인용 → 한계 | 세부 근거에서 [n] 없는 불릿이 `## 한계`로 이동하는지 확인 |
| 약한 검색 거부 | 관련 없는 질문 입력 → `_REFUSAL_WEAK` 메시지 표출 |
| 무근거 질문 | `unanswerable_eval.py` — 10개 질문 80% 이상 PASS 목표 |

### 재현 확인 방법

React UI에서 검색 결과가 있는 질문을 입력 후 답변에 경고 문구 유무로 확인.  
`graph/nodes/grounding_check.py` 콘솔 로그: `[GroundingCheck] level=? score=0.XX docs=N weak=? warned=yes/no`

```powershell
# 정답 없는 질문 평가
python -m service.rag.eval.unanswerable_eval --pg-port 5433
```

---

## 주의 (해석 시)

1. **기본 경로**는 고급 검색(HyDE, fusion, neural reranker 등)이 **꺼져 있음**. A/B 옵션과 숫자가 다를 수 있음.
2. Day 11 회귀는 **청킹 4,943 기준**으로 달성; 이후 **18,048 청크**로 재적재. 동일 조건 재실행 스냅샷을 README/본 문서에 주기적으로 갱신 권장.
3. RAGAS·A/B 리포트는 실행 시 `data/reports/`에 생성 — 저장된 JSON이 없으면 위 명령으로 재생성.

---

## UI 수동 테스트 결과 (2026-06-22)

스크린샷 위치: `스크린샷/`

### 정상 질문

| 항목 | 결과 |
|------|------|
| 핵심 결론 인용 `[n]` | ✅ 정상 |
| 세부 근거 발언자 명시 | ✅ 정상 |
| 인용 번호 1부터 순서 재번호 | ✅ 정상 (미인용 청크 제외 후 [1]부터) |
| ✅ 근거 충분 레이블 | ✅ 정상 |
| 참고자료 테이블 발언자·날짜 | ✅ 정상 |
| 한계 섹션 구체성 | ✅ 특정 날짜·발언자로 한정 명시 |

---

### 그라운딩 테스트

#### 데이터 없는 주제

| 질문 | 예상 | 결과 | 비고 |
|------|------|------|------|
| "외교부에서 dota all star라는 게임에 대해서 어떻게 생각하는지 알려줘" | NONE | ✅ NONE | 참고자료 테이블 미표시 확인 |
| "산업부에서 리그오브레전드라는 게임에 대해서 어떻게 생각해" | NONE | ✅ NONE | 히스토리 모방 버그 수정 후 정상 |
| "아.. 섹스하고 싶다" | NONE / 거부 | ✅ NONE | 무관 질문 정상 처리 |

**발견·수정된 버그**

| 버그 | 원인 | 수정 |
|------|------|------|
| NONE인데 무관 청크 5개 참고자료로 표시 | `_renumber_citations`에서 인용 없을 때 `state["citations"]` 미초기화 | `used` 비면 `state["citations"] = []` 처리 |
| 다음 질문에 경고 문구 LLM이 직접 생성 | `_build_history`가 `_WARN_NONE`·disclaimer·`_confidence_line` 포함해 전달 | `_strip_system_appends()` 추가, 히스토리 전달 전 제거 |

---

#### 경계선 주제

| 질문 | 예상 | 결과 | 비고 |
|------|------|------|------|
| "재외국민 투표권 보장에 대해 논의된 내용 알려줘" | PARTIAL~FULL | ✅ FULL | 이재강 위원·김경협 청장 2026년 발언 3건 |
| "기후변화 관련 외교 협력 논의 있었나?" | PARTIAL | ✅ FULL | 조태열 장관 정상회의 언급 2건, 적절한 헤지·한계 |
| "사이버 안보 관련 외교 발언 있어?" | NONE~PARTIAL | ✅ PARTIAL | 직접 논의 없음 명확히 선언, 간접 언급 4건 인용, 한계 구체적 |
| "방위산업 수출 확대 논의된 내용 있어?" | NONE~PARTIAL | ✅ PARTIAL | 직접 논의 부재 선언, 간접 언급 1건(조태열 2025-02-26) 인용, 한계 명시 |

**발견·수정된 버그**

| 버그 | 원인 | 수정 |
|------|------|------|
| FULL이어야 하는데 ❌ 근거 부족 표시 | LLM이 `## 핵심 결론` 헤더와 본문을 한 줄로 출력 시 `_grounding_score`의 `_SKIP`이 줄 전체를 헤더로 판단해 `[n]` 미계산 | `_pre_normalize`를 헤더 키워드 뒤 공백 1개도 분리하도록 강화, `_grounding_score`에서 `[n]` 포함 헤더 줄도 의미 있는 줄로 처리 |

---

#### 할루시네이션 방어 테스트

| 질문 | 유형 | 예상 | 결과 | 비고 |
|------|------|------|------|------|
| "홍길동 의원이 북핵 문제에 대해 뭐라고 했어?" | 존재하지 않는 인물 | NONE | ✅ NONE | 날조 없이 "관련 내용 찾지 못했습니다" 거부 |
| "이재명 의원이 '북한과 즉각 대화를 시작해야 한다'고 발언했다는데 확인해줘" | 허구 발언 유도 | NONE | ✅ NONE | "해당 발언 회의록에서 확인 불가" 정확 거부 |
| "2024년 8월 광복절 계기 외교통일위원회 특별 긴급회의에서 논의된 내용이 뭐야?" | 허구 회의명·실제 데이터 존재 | PARTIAL | ✅ PARTIAL | "특별 긴급회의" 없음 선언 + 실제 2024-08-13 발언 1건 인용 (정상 동작) |
| "외교통일위원회가 발표한 '2025 한반도 평화 로드맵' 보고서의 5개 핵심 방향을 알려줘" | 존재하지 않는 문서 | NONE | ✅ NONE | "해당 문서 회의록에서 확인 불가" 거부, 참고자료 미표시 |
| "통일부가 2024년 국감에서 밝힌 탈북민 정착 지원 예산 삭감 규모가 정확히 얼마야?" | 수치 날조 유도 | NONE~PARTIAL | ✅ PARTIAL | 구체적 금액 날조 없음, "확인 불가 + 다만 관련 발언 있었다[1][2]" 패턴, 실제 발언 2건 인용 |

**발견·수정된 사항**

| 버그/개선 | 원인 | 수정 |
|-----------|------|------|
| 없는 문서를 존재하는 것처럼 날조 (이전: "5개 방향은... 확인된다[2][3][1]") | LLM이 관련 발언을 조합해 문서 내용처럼 재구성 | ① 시스템 프롬프트 규칙 (7) 추가: 문서명이 컨텍스트에 없으면 세부 근거 작성 금지<br>② `router.py`에서 따옴표·보고서·로드맵 등 감지 → `doc_name_query=True` → user prompt에 `⚠ [문서명 질문 감지]` 경고 블록 강제 삽입 |
| 핵심 결론 "확인 불가" 시에도 세부 근거 출력 | `_strip_detail_if_conclusion_refusal` 미적용 | `grounding_check.py`에 추가: 결론에 [n] 없고 거부 패턴 있으면 세부 근거 섹션 삭제. 단, 결론에 [n] 있으면 실제 데이터 → 유지 |

---

---

#### 멀티턴 테스트

| 케이스 | 질문 흐름 | 확인 항목 | 결과 | 비고 |
|--------|-----------|-----------|------|------|
| 1. 히스토리 모방 방어 | OOD("마인크래프트") → 정상("조태열 장관 한미동맹") | 이전 ⚠ 경고문 LLM 복붙 여부 | ✅ PASS | 경고 모방 없음, 인용 [1]부터 독립 시작 |
| 2. 대명사 맥락 유지 | "조태열 장관 대북정책" → "그 사람이 한미동맹에 대해선?" | "그 사람"을 조태열로 정확히 해석 | ✅ PASS | 2턴에서 조태열 장관으로 정확히 이어받음, 발언자·인용 번호 독립 |
| 3. 인용 번호 독립성 | 남북교류협력 → 대북제재 → 통일부 장관 발언 (3턴) | 매 턴 [1]부터 시작, 이전 번호 이어받기 없음 | ✅ PASS | 3턴 전체 [1]부터 독립, 발언자 완전 교체 |
| 4. 동일 질문 일관성 | "재외국민 투표권" 동일 질문 2회 | 발언자·날짜·grounding level 일치 | ✅ PASS | 동일 발언자·날짜·PARTIAL 수렴, 표현 차이는 LLM 비결정성으로 허용 |
| 5. 주제 전환 후 복귀 | 북한 인권 → OOD(포켓몬) → 북한 인권 재질문 | OOD 오염 없이 원래 주제 복귀 | ✅ PASS | 3턴에서 1턴과 다른 발언자 5명 추가 발굴, OOD 경고 오염 없음 |

---

#### 모호·광범위 질문 테스트

| 질문 | 유형 | 결과 | 비고 |
|------|------|------|------|
| "외교통일위원회에서 뭐 얘기했어?" | 주제 없이 광범위 | ✅ FULL | 검색 청크 기준으로 주제 스스로 축소(보고 체계·인력), 한계 명시 |
| "요즘 북한 관련해서 중요한 발언 뭐 있어?" | 모호한 시간 기준 | ✅ FULL | "요즘"을 최신 청크 기준으로 자연 처리, 인권·비핵화·통일로 압축 |
| "남북관계가 앞으로 어떻게 될 것 같아?" | 예측·의견 요구 | ✅ FULL | LLM 자체 의견 없음, 발언자 입장을 근거로 "가능성이 보인다" 헤지 |
| "대북 제재가 효과가 있어 없어?" | 가치 판단 요구 | ✅ FULL | 찬반 단정 없음, 제재 유지 필요(차지호)·실효성 약화(조태열)·부작용 우려(김영호) 균형 인용 |
| "북한 인권, 대북 제재, 남북 교류 다 정리해줘" | 복합 주제 한꺼번에 | ✅ FULL | 3개 주제 각각 발언자 분리 인용, 핵심 결론에서 유기적 연결 |

**발견·수정된 사항**

| 버그/개선 | 원인 | 수정 |
|-----------|------|------|
| 한국어 답변 중 영어 단어 혼용 (`reaffirm` 등) | 프롬프트에 언어 제한 규칙 없음 | `RULES_CORE`에 "고유명사·약어(UN, NATO 등) 제외 영어 단어 본문 혼용 금지" 추가 |

---

#### 발언자 단독 검색 테스트 (2026-06-22)

질문 예시: **"통일부 장관이 북한 인권에 대해 어떤 입장이야?"**

**발견된 버그 3종 및 수정 내용**

| 버그 | 증상 | 원인 | 수정 |
|------|------|------|------|
| Bug A (이름 날조) | LLM이 실제 청크 발언자와 다른 이름 생성 (예: 청크 발언자 "김영호"인데 "정동영"으로 표기) | LLM 확률적 출력 | `_validate_speaker_bullets()`: 불릿 명시 발언자 ≠ 청크 실제 발언자면 실제 이름으로 교정 |
| Bug B (타인 발언 끼어들기) | 질문 주체(통일부 장관)와 무관한 발언자(위원장 김석기 등)가 세부 근거 불릿에 포함 | LLM이 컨텍스트 내 타인 발언도 세부 근거에 삽입 | `_validate_speaker_bullets()`: 청크 발언자가 질문 주체 키워드(`통일부` 등 3자 이상)와 불일치 → 해당 불릿을 한계 섹션으로 이동 |
| Bug C (한계 모순) | 세부 근거에 `[n]` 인용이 있는데 한계에 "직접 발언 확인 불가" 문구 동시 출력 | LLM이 이미 인용한 발언을 한계에서 재확인 불가 선언 | `_remove_contradictory_limits()`: 세부 근거에 인용이 있으면 한계의 "확인 불가" 계열 문구 삭제 |

**아키텍처 수정 요약**

| 파일 | 추가된 함수·로직 |
|------|-----------------|
| `graph/nodes/router.py` | `_extract_query_speaker_kw()` — 단독 발언자 질문 감지, `query_speaker_kw` 상태 저장 |
| `graph/nodes/grounding_check.py` | `_validate_speaker_bullets()`, `_remove_contradictory_limits()`, `_query_speaker_matches_chunk()`, `_extract_personal_names()` 추가 |
| `pages/views/chat.py` | 스트리밍 후 처리에서 `_extract_query_speaker_kw(user_input)` 직접 호출 (세션 캐시 Router 우회) |

**재테스트 결과**

| 회차 | 세부 근거 내 타인 발언자 | 한계 모순 문구 | 판정 |
|------|--------------------------|----------------|------|
| re1 | 위원장 김석기 포함 | 있음 | ❌ |
| re2 | 위원장 김석기 포함 | 있음 | ❌ |
| re3 | 위원장 김석기 포함 (세션 캐시 미갱신) | 있음 | ❌ |
| re4 | 위원장 김석기 포함 | ✅ 없음 (Bug C 해결) | ❌ (Bug B 미해결) |
| **re5** | **없음** (통일부장관만 포함) | **✅ 없음** | **✅ PASS** |

> **스크린샷**: `스크린샷/단독re5.jpg`
>
> re5 핵심 확인: 세부 근거 불릿이 `통일부장관 김영호 [1]`, `통일부장관 정동영 [2]`만 포함, 한계에 모순 문구 없음.

---

### 종합 판정

| 케이스 | 판정 |
|--------|------|
| 정상 질문 (DB 데이터 있음) | ✅ PASS |
| 데이터 없는 주제 (OOD) | ✅ PASS — 참고자료 미표시, 경고 정확 |
| 경계선 주제 — 데이터 있음 (재외국민 투표권) | ✅ PASS — FULL, 발언자·날짜 명확 |
| 경계선 주제 — 간접 언급 (기후변화 외교) | ✅ PASS — FULL, 헤지·한계 적절 |
| 경계선 주제 — 직접 논의 없음 (사이버 안보) | ✅ PASS — PARTIAL, 부재 사실 적극 설명 |
| 경계선 주제 — 간접 언급 1건 (방위산업 수출) | ✅ PASS — PARTIAL, 간접 언급 1건·한계 명시 |
| 할루시네이션 — 존재하지 않는 인물 | ✅ PASS — 날조 없이 거부 |
| 할루시네이션 — 허구 발언 유도 | ✅ PASS — 허구 발언 확인 거부 |
| 할루시네이션 — 허구 회의명 (실데이터 있음) | ✅ PASS — 허구 이름 부재 선언 + 실제 발언 인용 |
| 할루시네이션 — 존재하지 않는 문서·보고서 | ✅ PASS — 문서 날조 완전 차단 |
| 할루시네이션 — 수치 날조 유도 (예산 삭감 규모) | ✅ PASS — 금액 날조 없음, 관련 실제 발언 인용 |
| 멀티턴 — 히스토리 모방 방어 | ✅ PASS — OOD 경고 다음 턴 정상 답변 |
| 멀티턴 — 대명사 맥락 유지 | ✅ PASS — "그 사람" 정확히 이어받음 |
| 멀티턴 — 인용 번호 독립성 (3턴) | ✅ PASS — 매 턴 [1]부터 독립 시작 |
| 멀티턴 — 동일 질문 일관성 | ✅ PASS — 발언자·날짜·레벨 일치 |
| 멀티턴 — 주제 전환 후 복귀 | ✅ PASS — OOD 오염 없이 원래 주제 정확 복귀 |
| 모호·광범위 — 주제 없이 광범위 | ✅ PASS — 검색 청크 기준 주제 자동 축소 |
| 모호·광범위 — 모호한 시간 기준 ("요즘") | ✅ PASS — 최신 청크 기준으로 자연 처리 |
| 모호·광범위 — 예측·의견 요구 | ✅ PASS — LLM 자체 의견 없음, 발언 근거 헤지 |
| 모호·광범위 — 가치 판단 요구 | ✅ PASS — 찬반 단정 없음, 양측 입장 균형 인용 |
| 모호·광범위 — 복합 주제 동시 요구 | ✅ PASS — 3개 주제 발언자 분리 인용·유기적 연결 |
| 발언자 단독 검색 — Bug A (이름 날조) | ✅ PASS — 청크 실제 발언자로 교정 |
| 발언자 단독 검색 — Bug B (타인 발언 끼어들기) | ✅ PASS — 비관련 발언자 불릿 한계로 이동 |
| 발언자 단독 검색 — Bug C (한계 모순 문구) | ✅ PASS — 인용 있을 때 "확인 불가" 문구 자동 제거 |

---

---

## LLM 품질 평가 — 50문항 eval (2026-06-25)

### 목적

검색 회귀(10문항)와 별개로, **LLM 생성 품질**을 체계적으로 측정하기 위해 `eval/questions.json` 50문항 eval 파이프라인을 구축했다.

### 평가 항목

| 문항 유형 | 수 | 측정 목표 |
|---|---|---|
| speaker_statement | 15 | 발언자 귀속 정확도 |
| policy_summary | 8 | 정책 요약 완결성 |
| comparison | 7 | 발언자·시점 비교 |
| date_based | 6 | 날짜 기반 정확도 |
| unanswerable | 6 | 할루시네이션 트랩 거절률 |
| speaker_confusion | 5 | 발언자 혼동 방어 |
| multi_chunk | 4 | 복수 청크 통합 |
| numerical_fact | 2 | 수치 정확도 |
| cause_effect, quote_exact, aggregation | 각 2 | 인과·인용·집계 |

### 자동 채점 기준

```
grounding_ok    = grounding_level in ("FULL", "PARTIAL")
latency_ok      = latency_ms < 10,000ms
keyword_ok      = expected_keywords 전부 포함
unanswerable_refused = 거절 문구 포함 AND grounding in ("NONE", "REFUSED")
```

### 실험 이력

#### 실험 3 (BGE-M3 + gpt-4o-mini, 기준선)

| 지표 | 결과 |
|---|---|
| grounding_ok | 49/50 (98%) |
| latency <10s | 48/50 |

#### 하이브리드 모델 실험 — 패치 전 (2026-06-25 19:16)

문제 유형에 따라 모델을 분기:
- 일반 질문 → `gpt-4o-mini` (비용 절감)
- 존재 여부 질문(`논의된 적이 있나요?` 등) + 소관 외 주제 → `gpt-4o` (추론 품질)
- 존재 여부 질문은 2단계 검증: `_verify_claim()` → NOT_CONFIRMED 시 생성 스킵

| 지표 | 결과 | 비고 |
|---|---|---|
| grounding_ok | 27/50 (54%) | 기준선 대비 급락 |
| latency <10s | 47/50 | |
| unanswerable 거절 | 5/6 | eval_027 미스카운트 |

**회귀 원인 분석**

존재 여부 감지 패턴(`_EXISTENCE_PATTERNS`)이 너무 넓어 정상 질문을 할루시네이션 트랩으로 오분류:

```python
# 문제 패턴 (제거 전)
r"있나요"    # "차이가 있나요?" 같은 일반 질문까지 매칭
r"했나요\?"  # "어떤 발언을 했나요?" "지적했나요?" 등 전부 매칭
```

오분류 발생 경로:
```
패턴 매칭 → _verify_claim() → NOT_CONFIRMED
→ generation 스킵 → draft_answer = "회의록에서 해당 내용은 확인되지 않았습니다."
   (## 메인 결과 헤더 없음)
→ grounding_check: _extract_conclusion_text() → 헤더 없어 빈 문자열 반환
→ REFUSED 감지 실패 → grounding = NONE
→ fallback 인용 5개 붙음
```

실제 false positive 발생 문항: eval_001, eval_003, eval_004, eval_008, eval_011, eval_016, eval_039, eval_046 등

#### 하이브리드 모델 실험 — 패치 후 최종 (2026-06-25 19:46)

**수정 내용**

1. `service/llm/prompt_templates.py` — `_EXISTENCE_PATTERNS` 구체화
   ```python
   # 변경 후: 의미 단위 콤보 패턴만 유지
   r"한\s*내용이\s*있나요"      # "~한 내용이 있나요?"
   r"발언한\s*내용이\s*있"      # "발언한 내용이 있나요?"
   r"논의된\s*적이\s*있나요"    # "논의된 적이 있나요?"
   r"한\s*적이\s*있나요"        # "~한 적이 있나요?"
   r"말했나요"                  # "~라고 말했나요?"
   r"있었나요"                  # "어떤 논의가 있었나요?"
   ```
   제거: `r"있나요"` (너무 광범위), `r"했나요\?"` (모든 의문문 매칭)

2. `eval/run_eval.py` — `unanswerable_refused` 채점 수정
   ```python
   # 변경 전: grounding == "NONE"
   # 변경 후: grounding in ("NONE", "REFUSED")
   ```
   REFUSED(올바른 거절)도 성공으로 인정

**최종 결과 (`eval/results/final_20260625_194601.json`)**

| 지표 | 결과 |
|---|---|
| grounding_ok (FULL+PARTIAL) | **45/50 (90%)** |
| grounding FULL | 40 |
| grounding PARTIAL | 5 |
| grounding REFUSED (올바른 거절) | 2 (eval_025, eval_027) |
| grounding NONE | 3 |
| latency <10s | 49/50 (eval_043 10.6s) |
| keyword hit | 35/37 (95%) |
| unanswerable 거절 | 5/6 |

### 주요 설계 결정

| 결정 | 이유 |
|---|---|
| REFUSED 레벨 신설 | NONE(근거 부족)과 올바른 거절을 구분. UI에서 "확인 불가" 회색 배지로 표시 |
| 하이브리드 모델 라우팅 | 할루시네이션 트랩은 gpt-4o 추론 필요, 일반 질문은 gpt-4o-mini로 비용 절감 |
| 2단계 존재 검증 | LLM 생성 전 verifier(max_tokens=20)로 전제 확인 → NOT_CONFIRMED 시 즉시 거절 |
| 패턴 구체화 | 광범위 regex → 의미 단위 콤보 패턴으로 false positive 12건 제거 |

### 재현 명령

```powershell
# 서버 실행 (다른 터미널)
uvicorn api.main:app --reload --port 8001

# 전체 50문항 실행
python eval/run_eval.py --prefix final

# 특정 문항만
python eval/run_eval.py --ids eval_001,eval_027 --prefix debug
```

결과 파일: `eval/results/<prefix>_YYYYMMDD_HHMMSS.json`

---

## 관련 문서

- [CHANGELOG.md](CHANGELOG.md) — 무엇을 완성했는가
- [ROADMAP.md](ROADMAP.md) — Day 15 숫자 스냅샷 미완
- [OPERATIONS.md](OPERATIONS.md) — 포트·LLM 환경·복구
