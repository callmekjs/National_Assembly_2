# Architecture

**왜 이렇게 설계했는가** — 제품 서사, 레이어 구분, 기술 선택 이유.

---

## 프로젝트 서사·역할 분담

- **메인(사용자 가치)**: 국회 회의록 **근거 기반 질의응답(RAG)**  
  Streamlit **회의록 질의** → 적재(DB/벡터) 청크 검색 → **LLM 답변** → 참고 자료 `[n]`
- **전제(데이터)**: 수집·ETL·청킹·Postgres·pgvector 적재 — RAG의 **재료 저장소**
- **한 줄**: 「Streamlit 질문 → 적재 데이터 검색 근거 → LLM 답」. 검색 0건·근거 부족 시 사용자에게 명시.

CLI `qa_demo`는 보조 경로. 제품 스토리의 중심은 Streamlit + LangGraph입니다.

---

## 전체 구조

```text
[사용자·메인] Streamlit 회의록 질의 · LangGraph
   질문 → Retrieve(하이브리드·리랭크) → Generate(LLM) → 참고 자료 [n]
   (스트리밍 시: Retrieve까지 LangGraph → UI에서 chat_stream)

[전제·데이터 파이프라인]
원문 → Extract → Transform(정규화·청킹) → Load(문서·벡터)
   → Postgres + pgvector (embeddings_e5)
```

---

## LangGraph RAG 파이프라인

`graph/app_graph.py` — **9노드 직렬** 워크플로:

<!-- ARCH_NODES_START -->

> 🤖 자동 갱신: 2026-06-22 12:24


| 노드 | 역할 |
|------|------|
| Router | 검색 meta 기본값 병합 (`top_k`, `alpha`, …) |
| QueryRewrite | 질의 재작성 (현재 pass-through) |
| Retrieve | pgvector 하이브리드 검색 |
| Rerank | 후보 재정렬 |
| ContextTrim | LLM 입력 토큰에 맞게 컨텍스트 자르기 |
| Generate | LLM 답변 (또는 `skip_generate`로 UI 스트리밍 위임) |
| GroundingCheck | 문장 단위 `[n]` 인용 비율 측정 → FULL/PARTIAL/NONE + 경고 삽입 |
| Guardrail | 면책 문구 삽입 |
| Answer | 인용·최종 답변 정규화 |

<!-- ARCH_NODES_END -->

**QAState 주요 필드** (`graph/state.py`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `question` | str | 원질문 |
| `retrieved` / `reranked` | List[Dict] | 검색·리랭크 결과 |
| `draft_answer` | str | LLM 초안 (GroundingCheck에서 경고 삽입될 수 있음) |
| `grounded` | bool | `[n]` 인용 1개 이상 존재 |
| `grounding_score` | float | 의미 있는 줄 중 인용 있는 줄 비율 (0.0~1.0) |
| `grounding_level` | str | `"FULL"` / `"PARTIAL"` / `"NONE"` |
| `meta` | Dict | top_k, alpha, committee 등 파라미터 |

**설계 선택**
- **직선 그래프**: v1에서 분기·멀티에이전트보다 **재현 가능한 RAG 파이프라인** 우선
- **스트리밍 분리**: 검색은 LangGraph, 생성은 `chat_stream()` — Streamlit UX와 레이턴시 체감 개선
- **GroundingCheck 2단계 경고**: NONE이면 강한 경고(`⚠`), PARTIAL이면 안내(`ℹ`), FULL은 패스

---

## 검색·임베딩

### Dense 임베딩

- 모델: `intfloat/multilingual-e5-small` (384차원)
- 저장: `embeddings_e5` (pgvector HNSW)
- prefix: 질문 `query: `, 문서 `passage: `

### 기본 검색 경로

1. pgvector ANN (`<=>` 코사인)
2. 후보 `top_k × candidate_multiplier` (기본 50)
3. **하이브리드 재점수**: `alpha × 벡터 + (1-alpha) × lexical + 키워드 가점`
4. (옵션) reranker / MMR / fusion / HyDE / multi-query 등

**설계 선택**
- **벡터 먼저, 키워드는 재점수**: 별도 FTS 인덱스 없이 v1 복잡도 억제
- **고급 전략 opt-in**: 사이드바 체크박스 — 기본 경로 단순·회귀 안정, 실험은 명시적 활성화
- **도메인 규칙 가점**: 평가 난항 질의(통일부 장관, 정보 공유 제한) — 소규모 코퍼스에서 recall 확보

### 청킹

- 발언자 `◯` 단위 + 문장 경계 + 150자 overlap
- **이유**: 800자 기계 절단 시 발언 중간 단절 → 검색·인용 품질 저하

---

## LLM 생성

`service/llm/llm_client.py`

- **OpenAI API 우선** (`gpt-4o-mini` 기본) → 실패 시 **로컬 HF LoRA** (`Llama-3.2-3B`)
- `FORCE_LOCAL_LLM`, `OPENAI_ONLY`로 경로 제어
- 프롬프트: `service/llm/prompt_templates.py` — 발언자·날짜·인용 `[n]`·한계 섹션 규칙

### 멀티턴 히스토리

`llm_client.py` — `chat_stream` / `chat` 등 모든 함수에 `history: list[dict] | None` 파라미터.  
`chat.py` — `_build_history()`: 이전 Q&A 최대 3턴 추출, 인용 블록(`<!--RAG_REFERENCES-->` 이하) 제거 후 전달.

### 위원회 도메인 프롬프트

`COMMITTEE_DOMAIN` dict (5개 위원회) — `build_system_prompt(committee=)` 호출 시 `[도메인 컨텍스트]` 블록 삽입.  
`generate.py` — `state["meta"]["committee"]`를 읽어 전달.

**설계 선택**
- API 우선: 개발·데모 속도·품질. 로컬은 오프라인·키 없음 폴백
- **근거 기반 프롬프트**: hallucination 완전 차단은 아니나, GroundingCheck·면책·한계 섹션으로 완화
- **히스토리 토큰 절약**: 인용 JSON 블록 제거 — 히스토리 3턴이 토큰을 많이 차지하지 않도록

---

## 데이터 파이프라인 품질

| 메커니즘 | 목적 |
|----------|------|
| `contract.py` | 단계별 스키마 검증 |
| `quality.py` | 청크 품질 리포트 |
| `run_tracker.py` | 실행 이력·재현성 |
| incremental embed | 신규 청크만 임베딩 |
| upsert load | 재실행 안전 |

---

## 평가·회귀

- 고정 eval → `evaluate_retrieval` + `eval_report_day11.json`
- 확장 → RAGAS, A/B (`ab_compare`), 50문항 데이터셋
- **이유**: 포트폴리오·면접에서 **숫자로 방어** 가능하게

→ 수치·명령: [EVALUATION.md](EVALUATION.md)

---

## 의도적으로 미구현·보류

| 항목 | 이유 |
|------|------|
| ~~멀티턴 대화~~ | ✅ 2026-06-22 구현 완료 |
| FastAPI | Streamlit 메인 우선 |
| 전체 위원회 데이터 | 파이프라인·검색 품질 선행 |
| LangGraph 조건부 분기 | v1 직선 파이프라인으로 충분 |
| LLM 응답 캐시 | 비용 절감 필요 시 추후 |

---

## 관련 문서

- [README.md](README.md) — 실행 방법
- [OPERATIONS.md](OPERATIONS.md) — 운영·포트·복구
- [docs/dev-log/](docs/dev-log/) — 구현 상세
