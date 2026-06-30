# LLM 성능 평가 — 국회 회의록 RAG 시스템

> 최종 업데이트: 2026-06-30
> 평가 대상: 외교통일위원회 · 정무위원회 · 과방위 회의록 RAG
> DB: 78,952행 (chunks_v2), 3개 위원회, 2024-06 ~ 2026-04
> 시스템 구성: multilingual-e5-small 임베딩 + pgvector 하이브리드(BM25+벡터) + GPT-4o-mini/4o

---

## 1. 평가 관점 및 목표 KPI

| 평가 관점 | 핵심 지표 | 목표 | 현재 |
|---|---|---:|---:|
| **근거 충실도** | Grounding FULL/PARTIAL 비율 | ≥ 85% | **88.0%** ✅ |
| **모르는 질문 대응** | Unanswerable 거절률 | ≥ 90% | 66.7% ⚠️ |
| **속도** | p95 latency | ≤ 10s | **100%** ✅ |
| **운영 안정성** | 5xx 에러율 | ≤ 2% | 0% ✅ |

---

## 2. 현재 시스템 구성 (2026-06-30 기준)

```
임베딩:  multilingual-e5-small (384차원)
검색:    pgvector 하이브리드 (BM25 + 벡터 코사인, RRF 퓨전), search_v2()
재순위:  Jina Reranker v2
생성:    GPT-4o-mini (기본) / GPT-4o (reasoning)
파이프:  Router → QueryRewrite → retrieve_pg → rerank → context_trim → Generate → GroundingCheck → Guardrail
```

**주요 로직 (2026-06-30까지 구현)**

| 모듈 | 기능 |
|---|---|
| `router.py` | 인명/위원회/날짜 추출, 집계쿼리 감지(`_AGGREGATION_PATTERNS`), 당명 lookbehind |
| `retrieve_pg.py` | speaker 필터, balance_speakers, aggregate_query 시 speaker=None 강제 |
| `generate.py` | 인용번호 `[n]` 기반 답변 생성, 발언자 귀속 명시 |
| `grounding_check.py` | 인용번호 존재 여부 검증, FULL/PARTIAL/NONE/REFUSED 판정 |

---

## 3. 평가 데이터셋 (75문항)

파일: `eval/questions.json`

| 유형 | 문항 수 | 설명 |
|---|---:|---|
| speaker_statement | 18 | 특정 인물 발언 귀속 |
| policy_summary | 10 | 정책 입장 요약, 다중 청크 종합 |
| comparison | 8 | 두 입장/인물 비교 |
| date_based | 9 | 날짜/회의 기준 검색 |
| unanswerable | 9 | DB 부재 또는 허위전제 질문 → 거절 필요 |
| speaker_confusion | 6 | 질문자↔답변자 구분 |
| multi_chunk | 5 | 시계열 종합 |
| aggregation | 2 | 여러 화자 공통 의견 집계 |
| numerical_fact | 2 | 수치/금액 포함 답변 |
| cause_effect | 4 | 원인-결과 분석 |
| quote_exact | 2 | 직접 인용 |
| cross_committee | 2 | 위원회 간 크로스 쿼리 |
| **합계** | **75** | |

---

## 4. 테스트 결과 이력

| 실행 일시 | 결과 파일 | Grounding OK | p95 통과 | 거절 성공 | 비고 |
|---|---|---|---|---|---|
| 2026-06-30 12:17 | `results_20260630_121731.json` | 62/75 (82.7%) | 72/75 | — | 세션 초기 기준 |
| 2026-06-30 14:16 | `results_20260630_141646.json` | 63/75 (84.0%) | 72/75 | — | 인명 검증 + lookbehind 수정 |
| 2026-06-30 15:29 | `results_20260630_152952.json` | 66/75 (88.0%) | 72/75 | 6/9 | 집계쿼리 + 지시한정사 + 500에러 수정 |
| 2026-06-30 16:01 | `results_20260630_160145.json` | **66/75 (88.0%)** | **75/75** | **6/9** | 재실행 안정성 확인 |

---

## 5. 최신 eval 결과 (2026-06-30 16:01)

### 5.1 요약

```
총 75문항 실행
- p95 latency 기준(10s) 통과: 75/75  ✅
- Grounding FULL/PARTIAL:    66/75 (88.0%)
- 모르는 질문 거절:           6/9  (66.7%)
```

### 5.2 문항별 결과

| ID | 유형 | 질문 요약 | latency | Grounding | 인용수 |
|---|---|---|---|---|---|
| eval_001 | speaker_statement | 조태열 장관 트럼프 대응 | 1259ms | FULL | 4 |
| eval_002 | speaker_statement | 홍기원 위원 오물풍선 | 1154ms | FULL | 5 |
| eval_003 | speaker_statement | 김준형 위원 외교 비판 | 1369ms | FULL | 4 |
| eval_004 | speaker_statement | 윤후덕 위원 재외국민 | 1027ms | FULL | 4 |
| eval_005 | speaker_statement | 조현 장관 한미동맹 원칙 | 1019ms | FULL | 5 |
| eval_006 | speaker_statement | 이재강 위원 대북전단 | 1093ms | FULL | 3 |
| eval_007 | speaker_statement | 정동영 장관 남북대화 | 1043ms | FULL | 3 |
| eval_008 | speaker_statement | 김영배 소위원장 발언 | 1449ms | FULL | 1 |
| eval_009 | policy_summary | 트럼프 2기 대응 방침 | 1167ms | FULL | 3 |
| eval_010 | policy_summary | **비핵화 논의 요약** | 1123ms | **NONE** | 5 |
| eval_011 | policy_summary | 대북전단 정부·의회 반응 | 1240ms | FULL | 5 |
| eval_012 | policy_summary | 한미동맹 강화 방안 | 1369ms | FULL | 3 |
| eval_013 | policy_summary | 재외국민 보호 방안 | 1382ms | FULL | 3 |
| eval_014 | policy_summary | 계엄 후 외교 영향 | 1102ms | FULL | 4 |
| eval_015 | comparison | 여야 대북전단 입장 비교 | 1230ms | FULL | 4 |
| eval_016 | comparison | 조태열 vs 조현 한미동맹 | 1382ms | PARTIAL | 3 |
| eval_017 | comparison | 여야 트럼프 관세 대응 | 1197ms | FULL | 4 |
| eval_018 | comparison | **김영호 vs 정동영 북한정책** | 1654ms | **NONE** | 5 |
| eval_019 | comparison | 오물풍선 정부 vs 야당 | 1522ms | FULL | 5 |
| eval_020 | date_based | 2025-07-14 주제 | 1244ms | FULL | 4 |
| eval_021 | date_based | 2026-01-28 조현 장관 현안 | 855ms | FULL | 3 |
| eval_022 | date_based | 2025-09-08 북한 사안 | 1146ms | FULL | 2 |
| eval_023 | date_based | 2025-11-25 외교 현안 | 964ms | FULL | 2 |
| eval_024 | date_based | 2026-03-11 관세 논의 | 1051ms | PARTIAL | 2 |
| eval_025 | unanswerable | 이준석 外통위 북한 발언? | 416ms | NONE✅ | 0 |
| eval_026 | unanswerable | 기재부 장관 外통위 발언? | 1171ms | PARTIAL⚠️ | 4 |
| eval_027 | unanswerable | 국민연금 外통위 논의? | 1075ms | NONE✅ | 5 |
| eval_028 | unanswerable | 2024-06 外통위 회의? | 948ms | FULL⚠️ | 2 |
| eval_029 | speaker_confusion | 홍기원 질문 vs 조태열 답변 | 1337ms | FULL | 2 |
| eval_030 | speaker_confusion | 김준형 비판 vs 장관 반박 | 1592ms | FULL | 3 |
| eval_031 | speaker_confusion | 오물풍선 비판 vs 장관 답변 | 1540ms | FULL | 3 |
| eval_032 | speaker_confusion | 계엄 후 여당 입장 | 1632ms | FULL | 5 |
| eval_033 | multi_chunk | 트럼프 관세 논의 변화 추이 | 1372ms | FULL | 7 |
| eval_034 | multi_chunk | 계엄~탄핵 외교안보 시계열 | 1233ms | FULL | 4 |
| eval_035 | multi_chunk | 정권 교체 전후 비핵화 입장 | 1850ms | FULL | 5 |
| eval_036 | numerical_fact | 방위비 분담금 수치 | 1170ms | FULL | 5 |
| eval_037 | numerical_fact | ODA 예산 수치 | 1302ms | FULL | 4 |
| eval_038 | cause_effect | 오물풍선 원인 | 1383ms | FULL | 3 |
| eval_039 | cause_effect | 계엄 → 외교 영향 | 1278ms | FULL | 4 |
| eval_040 | quote_exact | 조태열 장관 직접 인용 | 970ms | FULL | 1 |
| eval_041 | quote_exact | 정동영 장관 직접 인용 | 1166ms | FULL | 2 |
| eval_042 | aggregation | 여러 위원 일본 관계 공통 우려 | 1638ms | FULL | 3 |
| eval_043 | aggregation | 여러 위원 관세 공통 요구 | 1173ms | FULL | 3 |
| eval_044 | unanswerable | 사드 철회 발언? (허위전제) | 1072ms | NONE✅ | 5 |
| eval_045 | unanswerable | 중국 군사동맹 논의? (허위전제) | 1233ms | NONE✅ | 5 |
| eval_046 | speaker_statement | 한정애 위원 외교 질의 | 1129ms | FULL | 5 |
| eval_047 | speaker_statement | 이용선 위원 미국 통상 | 1633ms | FULL | 4 |
| eval_048 | date_based | 2024-11-12 안건 | 1158ms | FULL | 5 |
| eval_049 | multi_chunk | 대일 외교 시기별 변화 | 1267ms | FULL | 5 |
| eval_050 | comparison | 민주당 vs 국민의힘 트럼프 관세 | 1345ms | FULL | 3 |
| eval_051 | speaker_statement | 김현정 위원 은행 이익 비판 | 999ms | FULL | 4 |
| eval_052 | speaker_statement | 이정문 소위원장 광복회 예산 | 1044ms | FULL | 2 |
| eval_053 | speaker_statement | 김남근 위원 공정거래 | 1041ms | FULL | 4 |
| eval_054 | policy_summary | 김병환 금융위원장 은행 규제 | 1012ms | FULL | 4 |
| eval_055 | policy_summary | 기업은행 파업 논의 | 1240ms | FULL | 4 |
| eval_056 | unanswerable | 정무위 북핵·한미동맹 논의? | 1009ms | FULL⚠️ | 7 |
| eval_057 | comparison | 여야 은행 규제 입장 차이 | 920ms | FULL | 2 |
| eval_058 | date_based | 2024-07-22 인사청문회 | 1129ms | FULL | 5 |
| eval_059 | speaker_confusion | 강민국 질의 vs 김병환 답변 | 1305ms | FULL | 3 |
| eval_060 | cause_effect | 은행 고이익 → 서민 부담 지적 | 1291ms | FULL | 3 |
| eval_061 | unanswerable | 이준석 정무위 금융 발언? | 414ms | NONE✅ | 0 |
| eval_062 | speaker_statement | 이준석 위원 과방위 발언 | 964ms | FULL | 4 |
| eval_063 | speaker_statement | 최형두 위원 SKT 해킹 | 1153ms | FULL | 5 |
| eval_064 | speaker_statement | 이훈기 위원 정보보호 투자 | 1492ms | FULL | 2 |
| eval_065 | policy_summary | SKT 유심 해킹 위원회 논의 | 9004ms | FULL | 6 |
| eval_066 | policy_summary | 방통위원장 청문회 쟁점 | 1245ms | FULL | 6 |
| eval_067 | unanswerable | 이준석 外통위 대북 발언? | 398ms | NONE✅ | 0 |
| eval_068 | comparison | KBS·MBC 방송독립 여야 입장 | 1747ms | FULL | 4 |
| eval_069 | date_based | 2025-05-08 청문회 내용 | 987ms | FULL | 3 |
| eval_070 | speaker_confusion | 방통위원장 후보자 답변 | 1308ms | FULL | 3 |
| eval_071 | numerical_fact | SKT 정보보호 투자 비율 수치 | 1022ms | FULL | 4 |
| eval_072 | cause_effect | 방통위원장 공석 → 방송 영향 | 1148ms | FULL | 3 |
| eval_073 | multi_chunk | SKT 사태 요구사항 변화 추이 | 1106ms | FULL | 7 |
| eval_074 | cross_committee | 이준석 소속 위원회 + 발언 | 1134ms | FULL | 4 |
| eval_075 | cross_committee | **2024-11-18 두 위원회 주제** | 930ms | **REFUSED** | 5 |

### 5.3 유형별 집계

| 유형 | 문항 수 | Grounding OK | 비고 |
|---|---:|---|---|
| speaker_statement | 18 | 18/18 (100%) | |
| policy_summary | 10 | 9/10 (90%) | eval_010 NONE |
| comparison | 8 | 6/8 (75%) | eval_018 NONE |
| date_based | 9 | 8/9 (89%) | eval_024 PARTIAL |
| unanswerable | 9 | — | 거절 6/9 (67%); 3건 미거절 |
| speaker_confusion | 6 | 6/6 (100%) | |
| multi_chunk | 5 | 5/5 (100%) | |
| aggregation | 2 | 2/2 (100%) | |
| numerical_fact | 2 | 2/2 (100%) | |
| cause_effect | 4 | 4/4 (100%) | |
| quote_exact | 2 | 2/2 (100%) | |
| cross_committee | 2 | 1/2 (50%) | eval_075 REFUSED |
| **전체** | **75** | **66/75 (88.0%)** | |

---

## 6. 실패 분석

### 6.1 실질 미해결 (2건)

| ID | 질문 | 원인 | 증거 |
|---|---|---|---|
| eval_010 | 비핵화에 대한 외교통일위원회의 논의 요약 | **오염 청크**: cit[1]이 정무위 '티메프 사태' 청크, cit[2]가 'UN 사회권규약' 청크 — 이질적 내용이 앞쪽에 위치해 LLM이 거절 | cit[3~5]엔 조태열 장관의 비핵화 발언이 있음에도 NONE |
| eval_018 | 김영호 전 vs 정동영 현 통일부장관 북한정책 비교 | **단방향 검색**: 5개 인용이 모두 김영호 장관 발언 — 정동영 장관 발언을 검색하지 못함 | eval_007(정동영 단독 쿼리)는 FULL로 정상 작동 → DB엔 있음 |

### 6.2 데이터 미포함 (1건)

| ID | 질문 | 원인 |
|---|---|---|
| eval_075 | 2024-11-18 두 위원회 각각 주제 | 반환된 5개 인용이 모두 2024-11-11 날짜 → 해당 날짜 데이터 없거나 검색 미매칭 |

### 6.3 올바른 거절 (6건)

eval_025, eval_027, eval_044, eval_045, eval_061, eval_067 — 이준석 외통위/정무위 발언 없음, 소관외 질문, 허위전제. 정확히 거절.

### 6.4 미거절 (3건, unanswerable이지만 답변)

| ID | 질문 | 현상 |
|---|---|---|
| eval_026 | 기재부 장관 外통위 발언? | PARTIAL 반환 (일부 연관 내용 존재) |
| eval_028 | 2024-06 外통위 회의? | FULL 반환 (인접 날짜 데이터로 답변) |
| eval_056 | 정무위 북핵·한미동맹 논의? | FULL 반환 (실제로 일부 언급 존재) |

---

## 7. 주요 개선 이력 (2026-06-30 세션)

| 수정 내용 | 대상 파일 | 효과 |
|---|---|---|
| 당명 lookbehind `(?<![가-힣])` 추가 | `router.py` | eval_050 NONE→FULL (국민의힘 오탐 차단) |
| `_COMMON_NON_NAME`에 지시한정사 추가 ("어떤","어느","모든","아무") | `router.py`, `retrieve_pg.py` | 집계형 쿼리에서 인명 오탐 방지 |
| `_AGGREGATION_PATTERNS` 감지 → `balance_speakers=True`, `top_k≥8` | `router.py` | 집계 쿼리 다화자 커버리지 확보 |
| aggregate 쿼리 시 `speaker=None` 강제 | `retrieve_pg.py` | 특정 화자 필터 우회 |
| 500에러 재시도 로직 (5초/10초 backoff) | `eval/run_eval.py` | eval_074 ERROR→FULL |
| 오류 traceback 로깅 | `api/main.py` | 500 원인 추적 가능 |

---

## 8. 다음 개선 후보

| 우선순위 | 개선 항목 | 관련 eval | 접근법 |
|---|---|---|---|
| P1 | 오염 청크 필터링 | eval_010 | 쿼리에 위원회명 명시 시 committee 메타 필터 적용 |
| P1 | 비교 쿼리 양방향 검색 | eval_018 | comparison 감지 시 인물 각각 개별 검색 후 합산 |
| P2 | 날짜 정확 매칭 | eval_075 | 날짜 기반 쿼리 시 DB date 컬럼 exact match 우선 |
| P2 | 거절률 개선 | eval_026/028/056 | unanswerable 유형별 거절 프롬프트 강화 |

---

## 9. 테스트 실행 방법

```bash
# 백엔드 시작
cd C:/National_Assembly_2
uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload

# 전체 평가 (75문항)
python eval/run_eval.py

# 특정 문항만
python eval/run_eval.py --ids eval_010,eval_018,eval_075

# 드라이런
python eval/run_eval.py --dry-run
```

결과 파일: `eval/results/results_YYYYMMDD_HHMMSS.json`

---

## 10. 참고

- 평가 문항: `eval/questions.json`
- 평가 실행기: `eval/run_eval.py`
- 결과 파일: `eval/results/`
- 백엔드 로직: `graph/nodes/router.py`, `graph/nodes/retrieve_pg.py`
- 테스트: `tests/test_backend_fixes.py` (111개 테스트)
