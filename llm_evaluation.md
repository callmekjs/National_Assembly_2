# LLM 성능 평가 — 국회 회의록 RAG 시스템

> 작성일: 2026-06-25  
> 평가 대상: 외교통일위원회 회의록 RAG (2025-04 ~ 2026-04, 35개 회의, 약 7,800 청크)  
> 시스템 구성: BGE-M3 임베딩 + pgvector 하이브리드 검색 + Jina Reranker + GPT-4o

---

## 1. 평가 관점 및 목표 KPI

| 평가 관점 | 핵심 지표 | 목표 |
|---|---|---:|
| **검색 성능** | Recall@4 (top_k=4 기준) | ≥ 85% |
| | MRR@4 | ≥ 0.70 |
| **근거 충실도** | Hallucination rate | ≤ 10% |
| | Grounding FULL 비율 | ≥ 70% |
| **인용 정확도** | Citation support rate | ≥ 90% |
| | Citation mismatch rate | ≤ 10% |
| **발언자 정확도** | Speaker attribution accuracy | ≥ 95% |
| | Speaker contamination rate (질문자↔답변자 혼동) | ≤ 5% |
| **모르는 질문 대응** | Unanswerable accuracy (거절 비율) | ≥ 90% |
| | False answer rate | ≤ 10% |
| **답변 품질** | Answer relevance (수동 1-5점) | ≥ 4.0 |
| | Completeness | ≥ 4.0 |
| **속도** | p95 latency | ≤ 10s |
| | p50 latency | ≤ 5s |
| **운영 안정성** | 오류율 | ≤ 2% |

---

## 2. 현재 시스템 구성 (평가 시점)

```
검색:   BGE-M3 임베딩 + pgvector (코사인 유사도 + BM25 RRF 퓨전)
재순위: Jina Reranker v2 (top_k=4 고정)
생성:   GPT-4o (스트리밍 + 자기검증 grounding check)
파이프: Router → QueryRewrite → retrieve_pg → rerank → context_trim → Generate → GroundingCheck
```

**변경 이력 (최근)**
- `JINA_API_KEY` 환경변수 수정으로 Jina 실제 호출 시작
- `top_k=4`로 축소 (5번째 청크 주제 이탈 방지)
- `_extract_claim_text()`로 search_text 정확도 개선
- PDF.js 뷰어 전환 (Method B, canvas 기반)

---

## 3. 평가 데이터셋 (35문항)

데이터셋 파일: `eval/questions.json`

### 문항 구성

| 유형 | 문항 수 | 설명 |
|---|---:|---|
| speaker_statement (특정 인물 발언) | 8 | 발언자 귀속 정확도 핵심 테스트 |
| policy_summary (정책 입장 요약) | 6 | 여러 청크 종합, 과장/일반화 방지 |
| comparison (두 입장 비교) | 5 | 당적 구분, 발언자 구분 능력 |
| date_based (날짜/회의 기준) | 5 | 날짜 교차 인용 방지 |
| unanswerable (회의록 없는 질문) | 4 | 거절 능력, 할루시네이션 방지 |
| speaker_confusion (발언자 혼동) | 4 | 질문자↔답변자 구분 |
| multi_chunk (다중 청크 필요) | 3 | 시계열 종합, 날짜 명시 능력 |
| **합계** | **35** | |

### 주요 문항 목록

| ID | 유형 | 질문 요약 | 핵심 채점 기준 |
|---|---|---|---|
| eval_001 | speaker_statement | 조태열 장관 - 트럼프 대응 | 장관 발언만 인용 |
| eval_002 | speaker_statement | 홍기원 위원 - 오물풍선 입장 | 여당/야당 발언 혼동 금지 |
| eval_005 | speaker_statement | 조현 장관 - 한미동맹 원칙 | 조태열↔조현 구분 |
| eval_007 | speaker_statement | 정동영 장관 - 남북대화 | 김영호↔정동영 구분 |
| eval_015 | comparison | 여야 대북전단 입장 비교 | 당적 명시 필수 |
| eval_016 | comparison | 조태열 vs 조현 한미동맹 비교 | 동일 직책 혼동 위험 |
| eval_025 | unanswerable | 이준석 의원 발언? (위원회 비소속) | 거절해야 함 |
| eval_028 | unanswerable | 2024년 6월 회의? (DB 없음) | 거절해야 함 |
| eval_029 | speaker_confusion | 홍기원 질문 vs 조태열 답변 구분 | Q↔A 구분 핵심 |
| eval_033 | multi_chunk | 트럼프 관세 논의 시간별 변화 | 날짜 명시 필수 |
| eval_035 | multi_chunk | 정권 교체 전후 비핵화 입장 변화 | 두 장관 대조 |

---

## 4. 채점 루브릭

### 4.1 자동 채점 (run_eval.py 처리)

| 항목 | 방법 | 기준 |
|---|---|---|
| 응답 속도 | 실측 ms | < 10,000ms ✅ / ≥ 10,000ms ⚠️ |
| Grounding level | API 응답 필드 | FULL / PARTIAL / NONE |
| 키워드 포함 | 문자열 포함 여부 | expected_keywords 전부 포함 |
| 거절 감지 (unanswerable) | 거절 표현 + NONE grounding | 거절 표현 있고 grounding=NONE |

### 4.2 수동 채점 기준 (1-5점)

**Faithfulness (근거 충실도)**
- 5: 모든 주장이 회의록에 명확히 근거함
- 4: 근거 있지만 경미한 과장 1건
- 3: 일반화/요약이 일부 원문에서 벗어남
- 2: 근거 없는 주장 1건 이상
- 1: 할루시네이션 명백 (없는 사실 생성)

**Speaker Accuracy (발언자 정확도)**
- 5: 모든 발언자 귀속 정확 + 당적 명시
- 4: 발언자 정확, 당적 일부 누락
- 3: 발언자 1명 오류 또는 질문자↔답변자 일부 혼동
- 2: 주요 발언자 귀속 오류
- 1: 동명이직 혼동 (조태열↔조현, 김영호↔정동영)

**Completeness (완전성)**
- 5: 질문의 모든 요소 다룸
- 4: 핵심 내용 포함, 부수 요소 1개 누락
- 3: 절반만 다룸
- 2: 질문의 핵심 1개 이상 누락
- 1: 질문과 관계없는 답변

**Overall (종합 1-5)**
- 위 세 항목 가중 평균: Faithfulness 40%, Speaker 35%, Completeness 25%

---

## 5. 테스트 실행 방법

### 서버 시작
```bash
# 백엔드
cd C:/National_Assembly_2
uvicorn api.main:app --reload --port 8000

# (선택) 프론트엔드
cd frontend && npm run dev
```

### 평가 실행
```bash
# 전체 35문항 실행
python eval/run_eval.py

# 특정 유형만 빠르게 확인 (예: unanswerable 4문항)
python eval/run_eval.py --ids eval_025,eval_026,eval_027,eval_028

# 드라이런 (API 호출 없이 문항 목록만)
python eval/run_eval.py --dry-run
```

결과는 `eval/results/results_YYYYMMDD_HHMMSS.json`에 저장됩니다.

---

## 6. 테스트 결과

> 아래 표는 `run_eval.py` 실행 후 여기에 붙여넣거나, 결과 JSON에서 수동 채점 완료 후 업데이트

### 6.1 자동 채점 요약

| 실행 일시 | 문항 수 | p95 latency | Grounding FULL | 키워드 OK | 거절 성공 |
|---|---|---|---|---|---|
| (미실행) | — | — | — | — | — |

### 6.2 문항별 결과

| ID | 유형 | 질문 | 응답시간 | Grounding | 인용수 | 키워드 | 수동점수 |
|---|---|---|---|---|---|---|---|
| eval_001 | speaker_statement | 조태열 장관 트럼프 대응 | — | — | — | — | — |
| eval_002 | speaker_statement | 홍기원 위원 오물풍선 | — | — | — | — | — |
| eval_003 | speaker_statement | 김준형 위원 외교 정책 비판 | — | — | — | — | — |
| eval_004 | speaker_statement | 윤후덕 위원 재외국민 | — | — | — | — | — |
| eval_005 | speaker_statement | 조현 장관 한미동맹 원칙 | — | — | — | — | — |
| eval_006 | speaker_statement | 이재강 위원 대북전단 | — | — | — | — | — |
| eval_007 | speaker_statement | 정동영 장관 남북대화 | — | — | — | — | — |
| eval_008 | speaker_statement | 김영배 소위원장 발언 | — | — | — | — | — |
| eval_009 | policy_summary | 트럼프 대응 방침 | — | — | — | — | — |
| eval_010 | policy_summary | 비핵화 논의 요약 | — | — | — | — | — |
| eval_011 | policy_summary | 대북전단 정부·의회 반응 | — | — | — | — | — |
| eval_012 | policy_summary | 한미동맹 강화 방안 | — | — | — | — | — |
| eval_013 | policy_summary | 재외국민 보호 방안 | — | — | — | — | — |
| eval_014 | policy_summary | 계엄 이후 외교 영향 | — | — | — | — | — |
| eval_015 | comparison | 여야 대북전단 입장 비교 | — | — | — | — | — |
| eval_016 | comparison | 조태열 vs 조현 한미동맹 | — | — | — | — | — |
| eval_017 | comparison | 여야 트럼프 관세 대응 비교 | — | — | — | — | — |
| eval_018 | comparison | 김영호 vs 정동영 북한 정책 | — | — | — | — | — |
| eval_019 | comparison | 오물풍선 정부 vs 야당 | — | — | — | — | — |
| eval_020 | date_based | 2025-07-14 주요 주제 | — | — | — | — | — |
| eval_021 | date_based | 2026-01-28 조현 장관 현안 | — | — | — | — | — |
| eval_022 | date_based | 2025-09-08 북한 사안 | — | — | — | — | — |
| eval_023 | date_based | 2025-11-25 외교 현안 | — | — | — | — | — |
| eval_024 | date_based | 2026-03-11 트럼프 관세 | — | — | — | — | — |
| eval_025 | unanswerable | 이준석 의원 발언? | — | — | — | — | — |
| eval_026 | unanswerable | 기재부 장관 외환 정책? | — | — | — | — | — |
| eval_027 | unanswerable | 국민연금 개혁 논의? | — | — | — | — | — |
| eval_028 | unanswerable | 2024년 6월 회의? | — | — | — | — | — |
| eval_029 | speaker_confusion | 홍기원 질문 vs 조태열 답변 | — | — | — | — | — |
| eval_030 | speaker_confusion | 김준형 비판 vs 장관 반박 | — | — | — | — | — |
| eval_031 | speaker_confusion | 오물풍선 비판 vs 장관 답변 | — | — | — | — | — |
| eval_032 | speaker_confusion | 계엄 후 여당 입장 | — | — | — | — | — |
| eval_033 | multi_chunk | 트럼프 관세 논의 변화 추이 | — | — | — | — | — |
| eval_034 | multi_chunk | 계엄~탄핵 외교안보 시계열 | — | — | — | — | — |
| eval_035 | multi_chunk | 정권 교체 전후 비핵화 입장 | — | — | — | — | — |

### 6.3 유형별 집계

| 유형 | 문항 수 | 평균 latency | Grounding OK | 수동 평균 |
|---|---|---|---|---|
| speaker_statement | 8 | — | — | — |
| policy_summary | 6 | — | — | — |
| comparison | 5 | — | — | — |
| date_based | 5 | — | — | — |
| unanswerable | 4 | — | 거절률: — | — |
| speaker_confusion | 4 | — | — | — |
| multi_chunk | 3 | — | — | — |
| **전체** | **35** | — | — | — |

---

## 7. 개선 우선순위 (테스트 후 업데이트)

| 우선순위 | 개선 항목 | 현재 상태 | 목표 | 접근법 |
|---|---|---|---|---|
| P0 | 발언자 혼동 (질문자↔답변자) | 미측정 | ≤ 5% | 청킹 시 발언자 전환 마커 강화 |
| P0 | 모르는 질문 거절 | 미측정 | ≥ 90% | 시스템 프롬프트 거절 조건 명확화 |
| P1 | 동명이직 장관 구분 | 미측정 | ≥ 95% | 날짜 필터 쿼리 구현 |
| P1 | Citation mismatch | 미측정 | ≤ 10% | top_k=4 유지, context_trim 개선 |
| P2 | p95 latency | 미측정 | ≤ 10s | Jina 캐시 또는 경량 reranker 대안 |
| P2 | Recall@4 | 미측정 | ≥ 85% | 청크 크기/겹침 최적화 |

---

## 8. 주요 실패 패턴 (테스트 후 업데이트)

> 실패 사례를 여기에 기록하여 재현 및 수정 추적

| 날짜 | 문항 ID | 실패 유형 | 구체 내용 | 수정 여부 |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 9. 참고

- 평가 문항: `eval/questions.json`
- 평가 실행기: `eval/run_eval.py`
- 결과 파일: `eval/results/results_*.json`
- 시스템 구성 현황: `api/main.py`, `graph/nodes/`
- 청킹 설계: `service/rag/vectorstore/pgvector_store.py`
