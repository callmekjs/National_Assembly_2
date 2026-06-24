# Roadmap

> MVP → 프로덕션 고도화 로드맵. 완료 내역 → [CHANGELOG.md](CHANGELOG.md) · 성능 근거 → [EVALUATION.md](EVALUATION.md) · 설계 → [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 현재 포커스

- [x] **대화 히스토리** — 멀티턴 대화 컨텍스트 (3-1) (2026-06-22)
- [x] **답변 신뢰도 표시** — 검색 hit 수·유사도 평균 UI 노출 (3-1) (2026-06-22)
- [x] 기본 검색 preset 고정 (fusion + neural reranker) — A/B 결과 반영 (2026-06-23)
- [ ] Day 14 배포·재현성 패키징
- [ ] Day 15 발표·데모 스크립트·숫자 스냅샷

---

## 1. 데이터 파이프라인 고도화

### 1-1. 데이터 확장 (보류 — 현재 데이터로 먼저 완성)

- [ ] ~~현재 외교통일위원회(55건) → 전체 위원회·전체 기간으로 확대~~
- [ ] ~~크롤링 스케줄러 추가~~

> 파이프라인 품질이 먼저. 데이터 확장은 1-2 완료 후.

### 1-2. 파이프라인 품질 강화 ✅ 완료

- [x] **청킹 전략 개선**: 고정 길이 → 발언자(◯) 단위 분리 + 문장 경계 분할 + 150자 overlap (2026-06-21)
- [x] **임베딩 incremental**: 신규 청크만 처리, --force 플래그로 전체 재처리 가능 (2026-06-21)
- [x] **스키마 계약(Contract)**: Extract/Transform/Load 각 단계 경계에서 필수 필드 자동 검증 (2026-06-21)
- [x] **데이터 품질 지표 추적**: 청크별 누락 필드 비율, 파싱 실패율, 짧은 청크 비율 모니터링 (2026-06-21)
- [x] **파이프라인 실행 이력 저장**: run_id 발급 → 각 실행 입력/출력/지표를 DB에 기록 (재현성) (2026-06-21)

### 1-3. 임베딩 모델 업그레이드 (나중에)

- [ ] 현재 `multilingual-e5-small` → `multilingual-e5-large` 또는 `bge-m3`로 교체
- [ ] 임베딩 차원 확장 후 recall@3 변화 비교 실험

> 1-2 완료 + 파이프라인 안정화 후 진행.

---

## 2. RAG 검색 품질 고도화

### 2-1. 검색 전략 ✅ 완료

- [x] **Multi-query Retrieval**: 질문 1개 → LLM으로 3~5개 변형 질문 생성 → 각각 검색 후 RRF로 결과 합산 (2026-06-21)
- [x] **HyDE (Hypothetical Document Embedding)**: 질문 → LLM이 가상 답변 생성 → 답변 임베딩으로 검색 (2026-06-21)
- [x] **Parent Document Retrieval**: 작은 청크(200자)로 검색 → 실제 LLM에는 부모 청크(800자) 전달 (2026-06-21)
- [x] **Contextual Compression**: 검색된 청크에서 질문과 무관한 부분을 LLM이 제거 후 전달 (2026-06-21)
- [x] **Step-back Prompting**: 구체 질문 → 더 추상적인 상위 질문으로 변환 후 검색 → 두 결과 합산 (2026-06-21)
- [x] **Fusion Retrieval (RRF)**: 벡터 검색 + BM25 키워드 검색 결과를 Reciprocal Rank Fusion으로 통합 (2026-06-21)

### 2-2. 리랭킹 고도화 ✅ 완료

- [x] **Neural Reranker (Cross-encoder)**: `BAAI/bge-reranker-v2-m3` 모델로 질문-청크 쌍 점수 재계산 (2026-06-21)
- [x] **LLM Reranker**: GPT-4o-mini에게 관련도 순서 재정렬 요청 (2026-06-21)
- [x] **MMR (Maximal Marginal Relevance)**: 유사도 높으면서 서로 다양한 결과 선택 — 중복 청크 억제 (2026-06-21)
- [x] **Score Normalization**: 벡터·BM25·lexical 점수를 min-max 정규화 후 앙상블 (2026-06-21)
- [x] **Multi-reranker Ensemble**: Neural + LLM reranker 결과를 RRF로 통합 (2026-06-21)
- [x] **리랭킹 전후 recall@3 비교 지표 자동 출력** (2026-06-21)

### 2-3. 평가 체계 ✅ 완료

- [x] **LLM 답변 품질 자동 평가 (RAGAS)**: faithfulness / answer_relevancy / context_precision / context_recall (2026-06-21)
- [x] **평가셋 확장**: 10개 → 50개 (대북정책·한미동맹·북핵·통일·외교안보 등, ground_truth 15개 포함) (2026-06-21)
- [x] **A/B 비교**: 8개 전략 조합 자동 비교 리포트 (2026-06-21)

---

## 3. LLM 생성 품질 고도화

### 3-1. 답변 품질

- [x] **스트리밍 응답**: Streamlit에서 답변이 실시간으로 타이핑되듯 출력 (2026-06-21)
- [x] **대화 히스토리**: 이전 질문·답변을 컨텍스트로 유지하는 멀티턴 대화 (2026-06-22)
- [x] **답변 신뢰도 표시**: 검색 hit 수·유사도 평균을 UI에 노출 (2026-06-22)

### 3-2. 재현성(Reproducibility) 개선

- [x] **temperature 인하 + seed 고정**: `OPENAI_TEMPERATURE=0` + `seed=42` 파라미터 → 동일 질문 동일 답변 (2026-06-24)
- [ ] **응답 캐시 (Exact Cache)**: 질문 hash → 답변 저장 → 재실행 시 LLM 호출 생략
- [ ] **구조화 출력 (JSON)**: `response_format=json_object`로 인용 번호 선택 안정화
- [ ] **Semantic Cache**: 유사 질문(cosine ≥ 0.95) 재활용 — 트래픽 생기면 그때 추가

> **진단 메모 (2026-06-24)**: 원인은 Rerank가 아닌 temperature=0.7. Neural Reranker는 이미 결정적(deterministic). 자세한 내용 → CHANGELOG.md

### 3-3. 프롬프트 고도화 ✅ 완료

- [x] 위원회별 도메인 특화 프롬프트 (외교·국방·경제 등 맥락 다름) (2026-06-22)
- [x] **근거 없으면 답 안 함** 강화: Grounding Check 노드 강화 (2026-06-22)
- [x] **출처 신뢰도 등급**: 인용 청크의 회의일·발언자 신뢰도 점수 표시 (2026-06-22)

---

## 4. 인프라·엔지니어링

### 4-1. API 레이어 ✅ 완료

- [x] **FastAPI 엔드포인트**: `POST /query`, `GET /meetings`, `GET /health` (2026-06-23)
- [x] API 문서 자동 생성 (Swagger UI `/docs`) (2026-06-23)

### 4-2. 모니터링·로깅 ✅ 완료

- [x] **쿼리 로그 저장**: query_logs 테이블 — 질문·답변·grounding_level·doc_count 누적 (2026-06-23)
- [x] **검색 실패 알림**: recall=0 자동 감지 (`is_recall_zero`) + `GET /logs/failures` 엔드포인트 (2026-06-23)
- [x] **응답 지연 모니터링**: retrieve_ms / generate_ms 단계별 측정 → state["latency_ms"] + DB 저장 (2026-06-23)

### 4-3. 테스트 ✅ 완료

- [x] 핵심 모듈 단위 테스트: `retriever`(12개), `chunker`(13개), `normalizer`(16개) — 41/41 PASS (2026-06-23)
- [ ] 파이프라인 E2E 통합 테스트 (미니 데이터셋)

---

## 5. UI/UX 개선

- [ ] **회의록 원문 열람 페이지** (`page2.py`): 위원회·날짜 필터로 원본 회의록 직접 조회
- [ ] **검색 결과 시각화**: 유사도 점수 막대그래프, 발언자별 분포 차트
- [ ] **질문 추천**: 적재 데이터 기반 예시 질문 자동 생성 및 버튼으로 노출

---

## Day 14 — 배포·재현성 패키징

> 디버깅·최적화 완료 후 실행. 상세 체크리스트: [docs/dev-log/milestones/day-14.md](docs/dev-log/milestones/day-14.md)

- [ ] `docker-compose` + 문서만으로 DB·(선택) 앱 기동 경로 명확
- [ ] compose 서비스·포트·볼륨 README 한 표 정리
- [ ] Postgres·`embeddings_e5` 헬스 체크 단일 CLI
- [ ] 클론 후 원데이 검증 노트 작성

---

## Day 15 — 발표·포트폴리오 마감

> 상세 체크리스트: [docs/dev-log/milestones/day-15.md](docs/dev-log/milestones/day-15.md)

- [ ] LLM/RAG 메인 서사 60초·5분 버전
- [ ] 데모 질문 3개(비교·분류·요약) 스크립트 + 실패 시 대사
- [ ] 아키텍처 다이어그램 1장
- [ ] 최신 `evaluate_retrieval` 스냅샷 ([EVALUATION.md](EVALUATION.md) 연동)
- [ ] 녹화 또는 면접 리허설 1회

---

## 우선순위 요약

| 순위 | 항목 | 임팩트 | 난이도 |
|------|------|--------|--------|
| ⭐⭐⭐ | 대화 히스토리 (작업 중) | UX·멀티턴 | 중 |
| ⭐⭐⭐ | 기본 검색 preset 고정 | 검색 품질·증명력 | 낮 |
| ⭐⭐⭐ | Day 14 재현성 패키징 | 포트폴리오 | 중 |
| ⭐⭐⭐ | Day 15 데모·발표 | 포트폴리오 | 중 |
| ⭐⭐ | FastAPI 레이어 | 완성도 | 중 |
| ⭐⭐ | 데이터 확장 (전체 위원회) | 커버리지 | 중 |
| ⭐ | 답변 신뢰도 표시 | UX | 낮 |
| ⭐ | e5-large / bge-m3 교체 | 검색 품질 | 높 |

---

## 작성 규칙

- 완료 시 `[x]`로 표시하고 [CHANGELOG.md](CHANGELOG.md)에 마일스톤 한 줄 추가
- 상세 작업 로그는 [docs/dev-log/](docs/dev-log/) 날짜별 파일에 기록
- **Day 14·Day 15**는 디버깅·최적화 이후에만 실행
