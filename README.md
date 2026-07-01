# 국회 회의록 근거 기반 질의응답 시스템 (RAG 프로토타입)

> 외교통일위원회·정무위원회·과학기술정보방송통신위원회 회의록을 벡터 DB에 적재하고,  
> 자연어 질문에 관련 발언을 검색해 LLM이 **출처 인용([n])과 함께** 답변하는 RAG 시스템.

---

## 프로젝트 목적

이 프로젝트는 **학습용 RAG 프로토타입**입니다.  
국회 회의록이라는 실제 도메인 데이터로 ETL → 벡터 DB → 하이브리드 검색 → LLM 생성 → 평가 파이프라인 전 과정을 직접 구현하며, 나중에 포트폴리오용 경량 버전으로 재구현하기 위한 기반을 마련하는 것이 목표입니다.

---

## 핵심 수치 (2026-06-30 최종)

| 지표 | 수치 |
|------|------|
| 적재 위원회 수 | 3개 (외교통일·정무·과기정통) |
| DB 총 청크 수 | **78,952행** (chunks_v2 테이블) |
| 임베딩 모델 | BAAI/bge-m3 (1024차원, Dense+Sparse) |
| LLM grounding_ok | **66/75 (88%)** — 75문항 eval, 4회차 |
| 단위 테스트 | **111/111 PASS** |
| 프론트엔드 배포 | Vercel (national-assembly-2.vercel.app) |
| 백엔드 배포 | 로컬 전용 (BGE-M3 2.2GB → 무료 클라우드 RAM 초과) |

---

## 시스템 아키텍처

```
사용자 질문 (React UI)
    │
    ▼
FastAPI  POST /query/stream  (SSE 스트리밍)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  LangGraph 파이프라인                 │
│                                                     │
│  Router → QueryRewrite → Retrieve → Rerank          │
│        → ContextTrim → Generate → GroundingCheck    │
└─────────────────────────────────────────────────────┘
         │                  │
         ▼                  ▼
  ┌─────────────┐    ┌────────────────┐
  │  pgvector   │    │  BM25 검색     │
  │  (BGE-M3)   │    │  (키워드)      │
  └─────────────┘    └────────────────┘
         │                  │
         └────────┬─────────┘
                  ▼
         RRF Fusion 결합
                  ▼
         Pure Python Rerank
         (점수 정규화 + 가중치)
                  ▼
    ┌─────────────────────────────┐
    │   하이브리드 모델 라우팅      │
    │  일반 질문   → GPT-4o-mini  │
    │  존재 여부   → GPT-4o       │
    │  소관 외 주제 → GPT-4o      │
    └─────────────────────────────┘
                  ▼
         [n] 출처 인용 + Grounding Check
         (FULL / PARTIAL / REFUSED / NONE)
```

---

## 데이터 파이프라인 (ETL 7단계)

```
incoming_data/**/*.pdf
    │
    ▼  Stage 1: Extract
    service/etl/extractor/extractor_v2.py
    → data/extract/*.jsonl  (3개 위원회 PDF 추출)
    │
    ▼  Stage 2: Normalize
    service/etl/transform/normalizer.py   # 텍스트 정규화·특수문자 처리
    │
    ▼  Stage 3: Parse / Chunking
    service/etl/transform/chunker_v2.py   # 발언자(◯) 단위 청킹 + 국면 태깅
    │
    ▼  Stage 4: Quality Check
    service/etl/contract.py / quality.py  # 스키마 검증 + 품질 리포트
    │
    ▼  Stage 5: Load (DB)
    service/etl/loader/jsonl_to_postgres.py  → chunks_v2 테이블
    │
    ▼  Stage 6: Embed
    service/etl/loader/embeddings_v2.py      → embeddings_e5_v2 테이블
    (BGE-M3 1024차원 Dense + Sparse 동시 생성)
    │
    ▼  Stage 7: Index
    BM25 SparseIndex 빌드 (서버 시작 시, ~30초)
    pgvector HNSW 인덱스 자동 생성
```

**데이터 적재 결과** (2026-06-30)

| 위원회 | 특이사항 |
|--------|---------|
| 외교통일위원회 | 대북·한미동맹·비핵화 |
| 정무위원회 | 금융·은행·공정거래·국가보훈 |
| 과학기술정보방송통신위원회 | AI·사이버보안·방통·공영방송 |
| **합계** | **78,952행** (embeddings_e5_v2와 1:1 정합) |

---

## RAG 파이프라인 (LangGraph 노드)

| 노드 | 역할 |
|------|------|
| `router` | 질문 유형 분류 (일반/비교/존재확인/OOD/문서명) + meta 기본값 병합 |
| `query_rewrite` | 검색 최적화 질문 변형 |
| `retrieve_pg` | BGE-M3 Dense + BM25 Sparse → RRF Fusion → Pure Python Rerank |
| `context_trim` | LLM 토큰 한도 내 컨텍스트 트리밍 |
| `generate` | 하이브리드 모델(gpt-4o-mini / gpt-4o) + [n] 인용 + 한계 섹션 |
| `grounding_check` | 문장 단위 [n] 인용 비율 측정 → FULL/PARTIAL/REFUSED/NONE |

### Grounding Level 정의

| 레벨 | 조건 | UI 배지 |
|------|------|---------|
| FULL | 인용 비율 > 0.6 | 녹색 "근거 충분" |
| PARTIAL | 0 < 인용 비율 ≤ 0.6 | 노란색 "일부 근거" |
| REFUSED | 인용 없음 + 거절 문구 감지 | 회색 "확인 불가" |
| NONE | 인용 없음 (일반) | 빨간색 "근거 부족" |

---

## 알고리즘 시리즈 (7개)

개발 후반부에 성능 개선을 위해 7개 알고리즘을 순차 구현했습니다.

| # | 알고리즘 | 효과 |
|---|---------|------|
| #1 | 집계 쿼리 감지 | "몇 번 언급" 류 질문 오탐 차단 |
| #2 | 지시 한정사 오탐 차단 | "~만 답해줘" 등 미트리거 |
| #3 | 당명 lookbehind 패턴 | 당명 앞 발언자 추출 정확도 향상 |
| #4 | BM25 하이브리드 RRF 결합 | Dense+Sparse 점수 융합, recall 향상 |
| #5 | Pure Python Rerank | 신경망 reranker 없이 성능 유지 |
| #6 | 비교 쿼리 멀티 검색 | A vs B 질문에서 양쪽 발언 균등 검색 |
| #7 | 시계열 정렬 | 비교/요약 결과 날짜순 정렬 |

---

## 평가 (eval)

### 4회차 eval 이력

| 회차 | 날짜 | 문항 수 | grounding_ok | 비고 |
|------|------|---------|--------------|------|
| 1회 | 2026-06-25 | 50 | 45/50 (90%) | 하이브리드 모델 도입 |
| 2회 | 2026-06-26 | 75 | 61/75 (81%) | 3개 위원회로 확장 |
| 3회 | 2026-06-29 | 75 | ~63/75 (84%) | 버그 6종 수정 후 |
| **4회 (최종)** | **2026-06-30** | **75** | **66/75 (88%)** | 알고리즘 #6·#7 적용 |

### 재현 방법

```powershell
uvicorn api.main:app --reload --port 8001
python eval/run_eval.py --prefix my_test
```

결과: `eval/results/my_test_YYYYMMDD_HHMMSS.json`

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| UI | React 19 + Vite |
| API | FastAPI + uvicorn (SSE 스트리밍) |
| RAG 오케스트레이션 | LangGraph |
| LLM | GPT-4o-mini (일반) / GPT-4o (존재확인·OOD) |
| 임베딩 | BAAI/bge-m3 (1024차원, Dense+Sparse 동시 인코딩) |
| 벡터 DB | PostgreSQL 17 + pgvector (HNSW 인덱스) |
| 키워드 검색 | BM25 (rank_bm25) |
| ETL | Python (pdfplumber, psycopg2) |
| 평가 | 자체 75문항 eval 파이프라인 |
| 단위 테스트 | pytest (111개) |
| 버전관리 | Git / GitHub (callmekjs/National_Assembly_2) |
| 프론트 배포 | Vercel |

---

## 프로젝트 구조

```
National_Assembly_2/
│
├── frontend/                       # React 프론트엔드
│   └── src/
│       ├── App.jsx                 # 메인 UI (SSE 스트리밍, 위원회 탭, 인용 배지)
│       ├── App.css
│       └── apiConfig.js            # VITE_API_BASE 환경변수
│
├── api/
│   └── main.py                     # FastAPI (SSE 스트리밍, 인메모리 캐시, multi-turn)
│
├── graph/                          # LangGraph RAG 파이프라인
│   ├── app_graph.py
│   ├── state.py
│   └── nodes/
│       ├── router.py
│       ├── query_rewrite.py
│       ├── retrieve_pg.py
│       ├── grounding_check.py
│       ├── generate.py
│       └── context_trim.py
│
├── service/
│   ├── etl/                        # 7단계 ETL 파이프라인
│   │   ├── extractor/extractor_v2.py
│   │   ├── transform/
│   │   │   ├── normalizer.py
│   │   │   └── chunker_v2.py
│   │   └── loader/
│   │       ├── jsonl_to_postgres.py
│   │       └── embeddings_v2.py
│   ├── llm/
│   │   ├── llm_client.py
│   │   └── prompt_templates.py
│   └── rag/
│       ├── retrieval/retriever.py
│       └── vectorstore/pgvector_store.py
│
├── eval/
│   ├── questions.json              # 75문항 (12개 유형)
│   ├── run_eval.py
│   └── results/
│
├── tests/                          # 111개 테스트
│
├── docs/
│   ├── evaluation/EVALUATION.md
│   ├── architecture/ARCHITECTURE.md
│   └── dev-log/milestones/        # Day 1-17 개발 이력
│
├── 스크린샷/
│   ├── 개발과정.jpg
│   └── make_diagram.py
│
└── .env.example
```

---

## 빠른 시작

### 1. 환경 준비

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env` 파일 생성 (`.env.example` 참고):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_REASONING_MODEL=gpt-4o
PG_HOST=localhost
PG_PORT=5433
PG_DB=skn_project
PG_PASSWORD=post1234
```

### 2. DB 기동

```powershell
docker start SKN18-3rd
```

### 3. FastAPI 백엔드 실행

```powershell
uvicorn api.main:app --reload --port 8001
```

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /query` | 질문 → 답변 + 인용 (동기) |
| `POST /query/stream` | SSE 스트리밍 답변 |
| `GET /health` | DB 연결 + 청크 수 확인 |
| `GET /meetings` | 적재된 회의 목록 |
| `GET /docs` | Swagger UI |

### 4. React 프론트엔드 실행

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속

### 5. 단위 테스트

```powershell
pytest tests/ -v
# 111/111 PASS
```

---

## 배포 현황

| 구성요소 | 상태 | URL |
|---------|------|-----|
| 프론트엔드 | Vercel 배포 완료 | national-assembly-2.vercel.app |
| 백엔드 | 로컬 전용 | http://localhost:8001 |

**백엔드 미배포 이유**: BGE-M3 모델(2.2GB RAM)이 무료 클라우드 티어 한도를 초과합니다.

---

## 주요 설계 결정

**발언자 단위 청킹**: `◯` 마커로 발언자 경계에서 분리해 한 발언이 끊기지 않게 합니다.

**BGE-M3 하이브리드**: Dense + Sparse 벡터를 단일 모델에서 동시 생성 후 BM25와 RRF로 결합합니다.

**하이브리드 모델 라우팅**: 존재 여부 질문은 gpt-4o + 2단계 검증, 일반 질문은 gpt-4o-mini로 비용을 절감합니다.

**REFUSED 레벨**: 올바른 거절을 NONE(근거 부족)과 구분해 UI에서 명확히 표시합니다.

**인메모리 캐시**: TTL 10분, 최대 200항목으로 동일 질문 재응답 속도를 5.8배 향상합니다.

---

## 알려진 한계

| 한계 | 내용 |
|------|------|
| 백엔드 미배포 | BGE-M3 RAM 요구량(2.2GB)이 무료 티어 초과 |
| 로그인/회원가입 없음 | 데모 사용자 단일 상태 |
| 커스텀 도메인 없음 | Vercel 기본 URL만 사용 |
| eval 실패 9건 | 위원회 필터 노이즈, 비교 쿼리 단일 검색, 날짜 불일치 등 미수정 |

---

## 포트폴리오 버전 계획

- BGE-M3 → OpenAI Embedding API (경량화, 무료 배포 가능)
- 전체 배포 (프론트 + 백엔드)
- 로그인/회원가입
- 커스텀 도메인

---

## 문서 맵

| 문서 | 내용 |
|------|------|
| [docs/evaluation/EVALUATION.md](docs/evaluation/EVALUATION.md) | 검색 회귀·LLM eval 상세·실험 이력 |
| [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | 설계 결정 근거 |
| [docs/dev-log/milestones/](docs/dev-log/milestones/) | Day 1-17 개발 이력 |
| [llm_evaluation.md](llm_evaluation.md) | 75문항 전체 결과 테이블 |
| [CHANGELOG.md](CHANGELOG.md) | 완료 이력 |
| [스크린샷/개발과정.jpg](스크린샷/개발과정.jpg) | 개발 전체 과정 다이어그램 |
