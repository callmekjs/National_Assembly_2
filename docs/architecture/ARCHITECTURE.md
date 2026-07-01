# Architecture

**왜 이렇게 설계했는가** — 제품 서사, 레이어 구분, 기술 선택 이유.

---

## 프로젝트 서사·역할 분담

- **메인(사용자 가치)**: 국회 회의록 **근거 기반 질의응답(RAG)**  
  React **회의록 질의** → FastAPI → LangGraph(검색·LLM) → **LLM 답변** → 참고 자료 `[n]`
- **전제(데이터)**: 수집·ETL·청킹·Postgres·pgvector 적재 — RAG의 **재료 저장소**
- **한 줄**: 「React 질문 → FastAPI → 적재 데이터 검색 근거 → LLM 답」. 검색 0건·근거 부족 시 사용자에게 명시.

---

## 전체 구조

```text
[사용자·메인] React 회의록 질의 · FastAPI · LangGraph
   질문 → Retrieve(하이브리드·리랭크) → Generate(LLM) → 참고 자료 [n]

[전제·데이터 파이프라인]
원문 → Extract → Transform(정규화·청킹) → Load(문서·벡터)
   → Postgres + pgvector (chunks_v2 + embeddings_e5_v2)
```

---

## LangGraph RAG 파이프라인

`graph/app_graph.py` — **7노드 직렬** 워크플로:

| 노드 | 역할 |
|------|------|
| Router | 질문 유형 분류 + meta 기본값 병합 (`top_k`, `alpha`, `committee`, …) |
| QueryRewrite | 질의 재작성 (현재 pass-through) |
| Retrieve | pgvector(BGE-M3 Dense) + BM25 Sparse → RRF Fusion → Pure Python Rerank |
| ContextTrim | LLM 입력 토큰에 맞게 컨텍스트 자르기 |
| Generate | LLM 답변 — 하이브리드 모델(gpt-4o-mini/gpt-4o) + `[n]` 인용 + 한계 섹션 |
| GroundingCheck | 문장 단위 `[n]` 인용 비율 측정 → FULL/PARTIAL/REFUSED/NONE + 경고 삽입 |
| Answer | 인용·최종 답변 정규화 |

**QAState 주요 필드** (`graph/state.py`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `question` | str | 원질문 |
| `retrieved` / `reranked` | List[Dict] | 검색·리랭크 결과 |
| `draft_answer` | str | LLM 초안 (GroundingCheck에서 경고 삽입될 수 있음) |
| `grounding_score` | float | 의미 있는 줄 중 인용 있는 줄 비율 (0.0~1.0) |
| `grounding_level` | str | `"FULL"` / `"PARTIAL"` / `"REFUSED"` / `"NONE"` |
| `meta` | Dict | top_k, alpha, committee 등 파라미터 |

**설계 선택**
- **직선 그래프**: 분기·멀티에이전트보다 재현 가능한 RAG 파이프라인 우선
- **SSE 스트리밍**: `/query/stream` 엔드포인트로 토큰 단위 실시간 출력, 체감 응답속도 향상

---

## 검색·임베딩

### Dense + Sparse 임베딩 (BGE-M3)

- 모델: `BAAI/bge-m3` (1024차원)
- 저장 테이블: `embeddings_e5_v2` (pgvector HNSW) — 테이블명은 이전 E5 모델 시절 명명, 실제 벡터는 BGE-M3 1024차원
- Dense: 코사인 유사도 (`<=>` 연산자)
- Sparse: BM25 (rank_bm25) 서버 시작 시 전체 청크 인덱스 빌드 (~30초)

### 검색 경로 (search_v2)

1. pgvector ANN (`<=>` 코사인) — Dense recall
2. BM25 키워드 검색 — Sparse recall
3. **RRF Fusion** (Reciprocal Rank Fusion) — Dense + Sparse 점수 결합
4. **Pure Python Rerank** — 메타데이터 가중치(발언자명·날짜·위원회 매칭) 재정렬
5. 위원회 필터 — `committee` 파라미터로 검색 범위 제한

**설계 선택**
- **BGE-M3**: 한국어 특화 멀티링구얼 모델, Dense + Sparse 동시 생성으로 별도 Sparse 모델 불필요
- **RRF**: Dense 단독 대비 날짜·발언자명 포함 질문에서 recall 향상

### 청킹 (`chunker_v2.py`)

- 발언자 `◯` 마커로 경계 감지, 발언자 단위 분리
- 국면 태깅: 발언 유형(질의/답변/보고 등) 분류 → `meeting_phase` 메타데이터 저장
- 발언이 긴 경우 문장 경계에서 추가 분할

**이유**: 고정 길이 청킹 시 발언 중간 단절 → 검색·인용 품질 저하

---

## LLM 생성 (`generate.py`)

### 하이브리드 모델 라우팅

```python
# gpt-4o 사용 조건
needs_reasoning_model(question, committee):
    1. 존재 여부 질문: "발언한 내용이 있나요?", "논의된 적이 있나요?" 등
       → _verify_claim() 2단계 검증: NOT_CONFIRMED 시 즉시 거절
    2. 소관 외 주제: 위원회별 금지 키워드

# 그 외 → gpt-4o-mini (비용 절감)
```

### 프롬프트 설계 (`prompt_templates.py`)

- `RULES_CORE`: 발언자 귀속·날짜·[n] 인용·한계 섹션 필수 규칙
- `COMMITTEE_DOMAIN`: 3개 위원회 도메인 컨텍스트 (관련 주제·소관 법률 등)
- `FEW_SHOT_EXAMPLES`: 예시 1개 (3→1로 축소, ~800 토큰 절감)
- 언어 규칙: 고유명사·약어(UN, NATO) 외 영어 단어 본문 혼용 금지

### 멀티턴 히스토리

- `api/main.py` `QueryRequest`: `history: Optional[list[dict]]`
- 프론트: 최근 6개 메시지를 `{role, content}` 형식으로 전송
- 인용 블록(`<!--RAG_REFERENCES-->` 이하) 제거 후 전달 (토큰 절약)

### 인메모리 캐시

- TTL 10분, 최대 200항목
- 캐시 키: SHA256(question + committee + top_k)
- 멀티턴 요청·REFUSED 응답은 캐시 제외
- 캐시 히트 시 응답 시간: 2초 (미캐시 대비 5.8배 빠름)

---

## Grounding Check (`grounding_check.py`)

```
grounding_score = 인용 있는 줄 수 / 의미 있는 줄 수
의미 있는 줄 = 길이 > 10자, 헤더/인용/마커 줄 제외
```

| 레벨 | 조건 | 동작 |
|------|------|------|
| FULL | score > 0.6 | 경고 없음 |
| PARTIAL | 0 < score ≤ 0.6 | `ℹ 일부 문장에 인용 번호 없음` 안내 삽입 |
| REFUSED | score = 0 + 거절 문구 감지 | 할루시네이션 방어 성공 — 세부 근거 섹션 삭제 |
| NONE | score = 0 | `⚠ 회의록에서 인용 번호 확인 불가` 경고 삽입 |

**추가 검증 로직**
- `_validate_speaker_bullets()`: 불릿 발언자 ≠ 청크 실제 발언자 → 이름 교정
- `_remove_contradictory_limits()`: 세부 근거에 [n] 있으면 한계의 "확인 불가" 문구 삭제
- `_strip_detail_if_conclusion_refusal()`: 결론 REFUSED 시 세부 근거 섹션 삭제

---

## 알고리즘 시리즈 (최종 7개)

| # | 위치 | 알고리즘 | 설명 |
|---|------|---------|------|
| #1 | `prompt_templates.py` | 집계 쿼리 감지 | `_is_aggregation_query()` — "몇 번 언급" 류 오탐 차단 |
| #2 | `prompt_templates.py` | 지시 한정사 오탐 차단 | `_is_directive_limiter()` — "~만 답해줘" 미트리거 |
| #3 | `prompt_templates.py` | 당명 lookbehind | `_PARTY_LOOKBEHIND` — 당명 앞 발언자 추출 정확도 |
| #4 | `retriever.py` | BM25 RRF 결합 | Dense + Sparse RRF Fusion |
| #5 | `retriever.py` | Pure Python Rerank | 신경망 모델 없이 메타데이터 가중치 재정렬 |
| #6 | `retriever.py` | 비교 쿼리 멀티 검색 | A vs B 질문 분리 검색 후 병합 |
| #7 | `retrieve_pg.py` | 시계열 정렬 | `_apply_chronological_sort()` — 결과 날짜순 정렬 |

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

| 평가 | 방법 | 결과 |
|------|------|------|
| 검색 회귀 (10문항) | `evaluate_retrieval` | recall@3 100% (Day 11 달성, 유지) |
| LLM 품질 (75문항) | `eval/run_eval.py` | 88% (66/75) — 4회차 |
| 단위 테스트 | pytest | 111/111 PASS |

---

## 배포 결정

| 구성요소 | 결정 | 이유 |
|---------|------|------|
| 프론트엔드 | Vercel 배포 | 정적 빌드 가능, 무료 티어 충분 |
| 백엔드 | 로컬 전용 | BGE-M3 2.2GB RAM → 무료 클라우드 티어 초과 |
| 포트폴리오 버전 | OpenAI Embedding API | API 호출로 경량화 → 전체 무료 배포 가능 |

---

## 의도적으로 미구현·보류

| 항목 | 이유 |
|------|------|
| 전체 위원회 데이터 | 3개 위원회로 충분한 파이프라인 검증 |
| LangGraph 조건부 분기 | v1 직선 파이프라인으로 충분 |
| LLM 응답 캐시 (Redis) | 인메모리 TTL 캐시로 대체 |
| 로그인/회원가입 | 데모 프로토타입 범위 초과 |
| Neural Reranker (bge-reranker) | Pure Python Rerank로 충분한 성능 확보 |

---

## 관련 문서

- [README.md](README.md) — 실행 방법, 핵심 수치
- [docs/evaluation/EVALUATION.md](docs/evaluation/EVALUATION.md) — 평가 상세
- [docs/dev-log/milestones/](docs/dev-log/milestones/) — Day 1-17 구현 상세
