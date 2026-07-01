# Evaluation

성능이 좋다는 **근거·재현 방법**을 정리합니다.

---

## 핵심 지표 요약 (2026-06-30 최종)

| 지표 | 수치 |
|------|------|
| 검색 recall@3 | **100%** (10/10, Day 11 달성·유지) |
| LLM grounding_ok | **66/75 (88%)** — 75문항 4회차 |
| 단위 테스트 | **111/111 PASS** |
| latency p95 | **75/75** < 10s |

---

## 검색 회귀 (고정 eval, 10문항)

| 시점 | score% | recall@3 | mrr@3 | 비고 |
|------|--------|----------|-------|------|
| Day 2 기준선 (2026-05-07) | 60 | 20 | 0.200 | 4문항 FAIL |
| Day 6 튜닝 후 | 90 | 80 | 0.667 | candidate_multiplier·키워드 가점 |
| Day 7 | 90 | 80 | 0.667 | 유형별 집계 추가 |
| **Day 11 (2026-05-09)** | **100** | **100** | **0.900** | 10/10 PASS |
| 청킹 재적재 후 (2026-06-21) | 100 | 100 | 0.900 | 유지 |

재현: `python -m service.rag.evaluate_retrieval --pg-port 5433`

---

## LLM 품질 평가 — 75문항 eval

### 문항 구성

| 문항 유형 | 수 | 측정 목표 |
|---|---|---|
| speaker_statement | 20 | 발언자 귀속 정확도 |
| policy_summary | 10 | 정책 요약 완결성 |
| comparison | 9 | 발언자·시점 비교 |
| date_based | 8 | 날짜 기반 정확도 |
| unanswerable | 8 | 할루시네이션 트랩 거절률 |
| speaker_confusion | 5 | 발언자 혼동 방어 |
| multi_chunk | 4 | 복수 청크 통합 |
| numerical_fact | 3 | 수치 정확도 |
| cause_effect, quote_exact, aggregation, cross_committee | 각 1-2 | 인과·인용·집계·교차 위원회 |

### 자동 채점 기준

```python
grounding_ok          = grounding_level in ("FULL", "PARTIAL")
latency_ok            = latency_ms < 10_000
keyword_ok            = expected_keywords 전부 포함
unanswerable_refused  = 거절 문구 포함 AND grounding in ("NONE", "REFUSED")
```

### 4회차 eval 이력

| 회차 | 날짜 | 문항 수 | grounding_ok | 주요 변경 |
|------|------|---------|--------------|---------|
| 1회 (50문항 기준선) | 2026-06-25 | 50 | 45/50 (90%) | 하이브리드 모델 라우팅 도입 |
| 2회 (75문항 확장) | 2026-06-26 | 75 | 61/75 (81%) | 3개 위원회 데이터 확장 |
| 3회 | 2026-06-29 | 75 | ~63/75 (84%) | 백엔드 버그 6종 수정 |
| **4회 (최종)** | **2026-06-30** | **75** | **66/75 (88%)** | 알고리즘 #6·#7 적용 |

### 4회차 결과 상세 (2026-06-30)

결과 파일: `eval/results/results_20260630_160145.json`

| 지표 | 수치 |
|------|------|
| grounding_ok (FULL+PARTIAL) | 66/75 (88%) |
| grounding FULL | 54 |
| grounding PARTIAL | 12 |
| grounding REFUSED (올바른 거절) | 4 |
| grounding NONE | 5 |
| latency <10s | 75/75 (100%) |
| unanswerable 거절 성공 | 7/8 (87.5%) |

### 실패 9건 분석

| ID | 증상 | 근본 원인 | 미수정 이유 |
|----|------|---------|-----------|
| eval_010 | NONE (비핵화 검색 실패) | 정무위 티메프 청크가 상위 랭크, 비핵화 청크 밀림 | 위원회 메타 필터 강화 필요 |
| eval_018 | PARTIAL (비교 한쪽 누락) | A vs B 비교 쿼리에서 B 발언자 검색 결과 없음 | 분리 검색 + 병합 로직 추가 필요 |
| eval_075 | NONE (날짜 불일치) | 질문 날짜 2024-11-18, DB 실제 날짜 2024-11-11 | 데이터 보완 또는 날짜 범위 검색 필요 |
| 나머지 6건 | NONE/PARTIAL | 경계선 케이스 또는 검색 품질 | 프롬프트 추가 조정 가능 |

---

## 개선 궤적

```text
Day 2:  recall@3 20%  — 후보 풀 부족, 도메인 키워드 미반영
Day 6:  recall@3 80%  — candidate_multiplier, 쿼리 확장, 키워드 가점
Day 11: recall@3 100% — 난항 질의 규칙·후보 배수 조정
2026-06-25: LLM eval 50문항 90% — 하이브리드 모델 도입
2026-06-26: 75문항 확장 → 81% (3위원회 데이터 증가로 노이즈 상승)
2026-06-29: 84% — 버그 6종 수정 (집계감지·지시한정사·당명lookbehind 등)
2026-06-30: 88% — 알고리즘 #6(비교쿼리 멀티검색) #7(시계열정렬) 적용
```

---

## Grounding Level 정의

| 레벨 | 조건 | UI 배지 |
|------|------|---------|
| FULL | 인용 비율 > 0.6 | 녹색 "근거 충분" |
| PARTIAL | 0 < 인용 비율 ≤ 0.6 | 노란색 "일부 근거" |
| REFUSED | 인용 없음 + 거절 문구 | 회색 "확인 불가" (올바른 거절) |
| NONE | 인용 없음 | 빨간색 "근거 부족" |

---

## 재현 명령

환경: `PG_PORT=5433` (Docker `SKN18-3rd`), `.env`에 DB·OpenAI 키 설정.

```powershell
# 백엔드 실행
uvicorn api.main:app --reload --port 8001

# 전체 75문항
python eval/run_eval.py --prefix my_test

# 특정 문항
python eval/run_eval.py --ids eval_010,eval_018 --prefix debug

# 검색 회귀
python -m service.rag.evaluate_retrieval --pg-port 5433
```

---

## 데이터 품질 (2026-06-30)

| 항목 | 값 |
|------|-----|
| 총 청크 수 | 78,952 |
| 위원회 수 | 3 (외교통일·정무·과기정통) |
| 임베딩 정합 | 78,952 (embeddings_e5_v2, 1:1) |
| speaker 채움률 | 98%+ |
| committee·date | 100% |

---

## UI 수동 테스트 케이스 (전체 PASS)

| 케이스 유형 | 결과 |
|-----------|------|
| 정상 질문 (DB 데이터 있음) | PASS |
| OOD 질문 (데이터 없음) | PASS — 참고자료 미표시 |
| 할루시네이션 — 존재하지 않는 인물 | PASS — 날조 없이 거부 |
| 할루시네이션 — 허구 발언 유도 | PASS — 허구 발언 확인 거부 |
| 할루시네이션 — 존재하지 않는 문서 | PASS — 문서 날조 완전 차단 |
| 할루시네이션 — 수치 날조 유도 | PASS — 금액 날조 없음 |
| 멀티턴 — 대명사 맥락 유지 | PASS — "그 사람" 정확히 이어받음 |
| 멀티턴 — 인용 번호 독립성 | PASS — 매 턴 [1]부터 독립 |
| 발언자 단독 검색 | PASS — 타인 발언자 필터링 |

---

## 관련 문서

- [llm_evaluation.md](../../llm_evaluation.md) — 75문항 전체 결과 테이블 (문항별 상세)
- [docs/architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) — 설계 결정 근거
- [CHANGELOG.md](../../CHANGELOG.md) — 완료 이력
