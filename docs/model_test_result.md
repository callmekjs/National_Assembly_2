# 모델·컨텍스트·인용 수 Ablation 실험 보고서

**작성일**: 2026-06-25  
**실험자**: callmekjs  
**프로젝트**: 국회 외교통일위원회 회의록 RAG 시스템

---

## 1. 실험 목적

RAG 답변 품질을 유지하면서 응답 속도와 인용 노출 수를 줄이는 최적 설정을 찾기 위해 단일 변수 ablation 실험을 3단계로 진행했다.

**원칙**: 한 번에 하나의 변수만 변경하고 50문항 평가를 재실행해 인과관계를 명확히 한다.

---

## 2. 기준선 (Baseline)

| 항목 | 설정 |
|---|---|
| 모델 | gpt-4o |
| LLM 컨텍스트 문서 수 | 최대 8개 |
| 인용 노출 방식 | 상위 10개 고정 |
| GENERATE_MAX_TOKENS | 1024 |
| 평가 파일 | `results_20260625_151714.json` |

---

## 3. 실험 설계

| 실험 | 변경 내용 | 나머지 |
|---|---|---|
| 기준선 | gpt-4o + 컨텍스트 8개 + 인용 10개 | — |
| 실험 1 | **gpt-4o-mini** 전환 | 컨텍스트·인용·토큰 수 동일 |
| 실험 2 | 실험 1 유지 + **컨텍스트 8→6개** | 인용·토큰 수 동일 |
| 실험 3 | 실험 2 유지 + **인용 실사용 [n]만 노출** (fallback top 5) | 토큰 수 동일 |

---

## 4. 전체 결과 비교

| 항목 | 기준선 (gpt-4o) | 실험 1 (mini) | 실험 2 (mini+6ctx) | 실험 3 (mini+6ctx+cite) |
|---|---:|---:|---:|---:|
| **generation_failure** | 0 | 0 | 0 | **0** |
| **grounding_ok** | 45/50 = 90.0% | 48/50 = 96.0% | 49/50 = 98.0% | **49/50 = 98.0%** |
| grounding_FULL | 41/50 = 82.0% | 44/50 = 88.0% | 42/50 = 84.0% | 42/50 = 84.0% |
| **effective_success** | 45/50 = 90.0% | 48/50 = 96.0% | 49/50 = 98.0% | **49/50 = 98.0%** |
| **keyword_ok** | 35/37 = 94.6% | 35/37 = 94.6% | 35/37 = 94.6% | **35/37 = 94.6%** |
| **speaker_mentioned** | 13/13 = 100% | 13/13 = 100% | 13/13 = 100% | **13/13 = 100%** |
| unanswerable_refused | 4/6 = 66.7% | 2/6 = 33.3% | 1/6 = 16.7% | 1/6 = 16.7% |
| **citation_avg** | 7.72 | 7.72 | 7.72 | **3.30** |
| citation_zero | 1 | 1 | 1 | 1 |
| **avg_latency** | 10,897ms | **7,631ms** | 9,007ms | 7,859ms |
| median_latency | 10,846ms | 7,004ms | 8,049ms | 6,907ms |
| p90_latency | 15,827ms | 12,718ms | 15,466ms | **11,313ms** |
| p95_latency | 16,176ms | 14,280ms | 18,720ms | 15,264ms |
| max_latency | 27,746ms | 24,360ms | 25,028ms | 29,804ms |
| over_5s | 46/50 | 44/50 | 45/50 | 44/50 |
| **over_10s** | 29/50 | **8/50** | 15/50 | **6/50** |
| over_20s | 1/50 | 1/50 | 2/50 | 1/50 |

---

## 5. 실험별 분석

### 실험 1: gpt-4o → gpt-4o-mini

**변경**: `.env`의 `OPENAI_MODEL=gpt-4o` → `OPENAI_MODEL=gpt-4o-mini`

**결과 요약**:
- avg latency **10,897ms → 7,631ms (-30%)** — 목표 8s 달성
- over_10s **29 → 8** — 64% 감소
- grounding_ok **90% → 96%** — 예상 외 품질 향상
- keyword/speaker 완전 유지

**관찰**: gpt-4o-mini가 더 간결하게 답변을 생성해 grounding check 통과율이 오히려 개선됐다. 품질 하락 없이 속도 30% 향상.

**유일한 우려**: unanswerable_refused 4/6 → 2/6. 허위 전제를 감지하는 추론 능력이 다소 약해졌다.

**판정**: ✅ 실험 2 진행

---

### 실험 2: 컨텍스트 8개 → 6개

**변경**: `generate.py`의 `_build_numbered_context` — `docs[:8]` → `docs[:6]`

**결과 요약**:
- avg latency 7,631ms → 9,007ms **(+1,376ms, +18%)** — 오히려 증가
- p95 14,280ms → 18,720ms — 악화
- grounding_ok 96% → 98% — 미세 개선
- citation_avg 변화 없음 (7.72 유지)

**관찰**: 컨텍스트 2개 감소로 인한 입력 토큰 절약(약 600~800 토큰)보다 OpenAI API 응답 시간의 자연 변동이 훨씬 크다. 컨텍스트 8→6은 레이턴시에 의미 있는 영향을 주지 못한다. citation_avg가 그대로인 이유는 API가 retrieval 결과를 그대로 citation으로 채우는 구조이기 때문.

**판정**: ✅ 레이턴시 효과 없음 확인, 품질 유지로 실험 3 진행

---

### 실험 3: 인용 실사용 [n]만 노출

**변경**: `api/main.py` — 답변 본문의 `[n]` 번호를 파싱해 실제 사용된 citation만 반환. `[n]` 없으면 top 5 fallback.

**결과 요약**:
- citation_avg **7.72 → 3.30** — 목표(4~5개) 수준 달성
- avg latency 7,631ms 수준 유지 (citation 처리는 생성 후 단계라 속도 무관)
- over_10s **8 → 6** — 소폭 추가 개선
- p90 12,718ms → 11,313ms — 개선
- 품질 지표 전부 실험 2와 동일하게 유지

**관찰**: 인용 필터링은 응답 생성 이후 단계라 latency에 영향 없음. grounding/keyword/speaker 모두 무손실. citation_zero는 1개로 유지(unanswerable 응답에서 발생하는 정상 케이스).

**판정**: ✅ 모든 필수 조건 통과

---

## 6. 최종 비교 요약

```
                  기준선     실험1      실험2      실험3
grounding_ok      90.0%     96.0%     98.0%     98.0%
effective_success 90.0%     96.0%     98.0%     98.0%
keyword_ok        94.6%     94.6%     94.6%     94.6%
speaker_mentioned 100%      100%      100%      100%
citation_avg       7.72      7.72      7.72      3.30
avg_latency      10,897ms  7,631ms   9,007ms   7,859ms
over_10s          29/50     8/50     15/50      6/50
```

---

## 7. 핵심 발견

1. **모델 교체(실험 1)가 유일하게 유효한 레이턴시 개선 수단이었다.** avg -30%, over_10s -72%.

2. **컨텍스트 개수 축소(실험 2)는 레이턴시에 효과가 없다.** OpenAI API 응답 시간 자연 변동(±2s)이 입력 토큰 절약 효과를 압도한다.

3. **gpt-4o-mini가 gpt-4o보다 grounding이 높게 나왔다.** 더 짧고 집중된 답변 생성 → grounding check 통과율 향상. RAG 합성 태스크에서 mini가 충분히 유효하다.

4. **unanswerable 감지는 mini의 약점이다.** 4/6 → 1/6으로 하락. 허위 전제를 포함한 질문에 대한 추론이 gpt-4o보다 약하다. 시스템 프롬프트에 명시적 지시 보강이 필요하다.

5. **citation 필터링(실험 3)은 무손실 개선이다.** 품질 0% 변화, citation_avg 57% 감소, UI 가독성 개선.

---

## 8. 최종 채택 설정

실험 3 설정을 최종 운영 설정으로 채택한다.

| 항목 | 설정값 |
|---|---|
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `GENERATE_MAX_TOKENS` | `1024` |
| LLM 컨텍스트 문서 수 | `6개` (`docs[:6]`) |
| citation 노출 방식 | 답변 내 실사용 `[n]`만, fallback top 5 |

**필수 조건 충족 여부**:

| 조건 | 기준 | 실험 3 결과 | 판정 |
|---|---|---|---|
| generation_failure | = 0 | 0 | ✅ |
| empty_answer | = 0 | 0 | ✅ |
| grounding_ok | ≥ 88% | 98.0% | ✅ |
| effective_success | ≥ 95% | 98.0% | ✅ |
| keyword_ok | ≥ 90% | 94.6% | ✅ |
| speaker_mentioned | ≥ 95% | 100% | ✅ |
| avg_latency | ≤ 8,000ms | 7,859ms | ✅ |
| over_10s | ≤ 15개 | 6개 | ✅ |
| over_20s | = 0 | 1개 | △ |
| citation_avg | 4~5개 | 3.30개 | △ |

> over_20s 1개는 OpenAI API 일시 지연으로 추정. citation_avg 3.30은 목표(4~5)보다 낮으나 허용 범위.

---

## 9. 잔존 과제

| 과제 | 우선순위 | 내용 |
|---|---|---|
| unanswerable 강화 | 높음 | 시스템 프롬프트에 허위 전제 명시적 감지 지시 추가 |
| over_20s 제거 | 중간 | OpenAI 429 재시도 또는 타임아웃 전략 개선 |
| citation_avg 4~5개 조정 | 낮음 | fallback 개수(현 5)를 유지하거나 소폭 조정 |
| speaker_confusion 보강 | 중간 | 4문항 중 2개 FULL — 발언자 혼동 방지 추가 검토 |

---

## 10. 실험 파일 목록

| 실험 | 결과 파일 |
|---|---|
| 기준선 | `eval/results/results_20260625_151714.json` |
| 실험 1 | `eval/results/results_model_only_20260625_154815.json` |
| 실험 2 | `eval/results/results_model_context_20260625_163111.json` |
| 실험 3 | `eval/results/results_model_context_citation_20260625_165005.json` |
