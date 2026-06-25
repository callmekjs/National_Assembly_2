# 국회 회의록 근거 기반 질의응답 시스템

> 외교통일위원회 회의록 55건을 벡터 DB에 적재하고,  
> 질문하면 관련 발언을 검색해 LLM이 **출처 인용과 함께** 답변하는 RAG 시스템.

---

## 핵심 수치 (2026-06-25 기준)

| 지표 | 수치 |
|------|------|
| 데이터 | 외교통일위원회 회의록 55건 |
| 청크 수 | 18,048개 (발언자 단위) |
| recall@3 | **100%** (10/10) |
| LLM grounding_ok | **45/50 (90%)** — 50문항 eval |
| LLM latency p95 | **49/50** < 10s |
| keyword 정확도 | **35/37 (95%)** |
| 할루시네이션 거절 | **5/6** unanswerable 정확 거절 |
| RAGAS faithfulness | **0.9857** |
| 단위 테스트 | **41/41 PASS** |

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
         Neural Reranker
         (BAAI/bge-reranker-v2-m3)
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

## 데이터 파이프라인

```
incoming_data/외교통일위원회/*.pdf
    │
    ▼  Extract
    service/etl/extractor/extractor.py
    → data/extract/extracted.jsonl  (55건)
    │
    ▼  Transform
    service/etl/transform/normalizer.py   # 텍스트 정규화
    service/etl/transform/chunker_v2.py   # 발언자(◯) 단위 청킹
    → data/transform/final/chunks.jsonl  (18,048건)
    │
    ▼  Load
    service/etl/loader/jsonl_to_postgres.py  → chunks 테이블
    service/etl/loader/embeddings.py         → embeddings_bge 테이블
    (BAAI/bge-m3-unsupervised, 1024차원, 하이브리드 검색용)
```

**파이프라인 품질 보증**
- chunk_id·content 100% / speaker 98.6% / meeting_date 100%
- 중복 임베딩 0건 (incremental 방식)

---

## RAG 파이프라인 (LangGraph 노드)

| 노드 | 역할 |
|------|------|
| `router` | 질문 유형 분류 (일반 / 비교 / 발언자 단독 / OOD / 문서명) |
| `query_rewrite` | LLM으로 검색 최적화 질문 변형 |
| `retrieve_pg` | BGE-M3 하이브리드(Dense+Sparse) + Neural Reranker |
| `context_trim` | 토큰 초과 방지 컨텍스트 트리밍 |
| `generate` | 하이브리드 모델(gpt-4o-mini / gpt-4o) + `[n]` 인용 |
| `grounding_check` | 근거 수준 평가 (FULL / PARTIAL / REFUSED / NONE) |

### Grounding Level

| 레벨 | 조건 | UI 배지 |
|------|------|---------|
| FULL | 인용 비율 > 0.6 | 녹색 "근거 충분" |
| PARTIAL | 0 < 인용 비율 ≤ 0.6 | 노란색 "일부 근거" |
| REFUSED | 인용 없음 + 거절 문구 감지 | 회색 "확인 불가" |
| NONE | 인용 없음 (일반) | 빨간색 "근거 부족" |

### 하이브리드 모델 라우팅

```python
needs_reasoning_model(question):
    존재 여부 질문  ("논의된 적이 있나요?", "발언한 내용이 있나요?" 등)
    소관 외 주제   (국민연금, 조세정책, 검찰개혁 등)
    → gpt-4o  (2단계 존재 검증 포함)

그 외 → gpt-4o-mini
```

---

## 프로젝트 구조

```
National_Assembly_2/
│
├── frontend/                       # React 프론트엔드
│   └── src/
│       ├── App.jsx                 # 메인 UI (SSE 스트리밍, PDF 뷰어, 인용 배지)
│       └── App.css
│
├── api/
│   └── main.py                     # FastAPI (POST /query, POST /query/stream, GET /health 등)
│
├── graph/                          # LangGraph RAG 파이프라인
│   ├── app_graph.py
│   ├── state.py
│   └── nodes/
│       ├── router.py
│       ├── query_rewrite.py
│       ├── retrieve_pg.py
│       ├── grounding_check.py      # FULL/PARTIAL/REFUSED/NONE 판정
│       ├── generate.py             # 하이브리드 모델 + 2단계 존재 검증
│       └── context_trim.py
│
├── service/
│   ├── etl/                        # 데이터 파이프라인 (Extract→Transform→Load)
│   ├── llm/
│   │   ├── llm_client.py           # OpenAI 클라이언트 (스트리밍 지원)
│   │   └── prompt_templates.py     # 도메인 특화 프롬프트 + 라우팅 감지 함수
│   └── rag/
│       ├── retrieval/retriever.py  # BGE-M3 하이브리드 검색
│       └── vectorstore/pgvector_store.py
│
├── eval/                           # LLM 품질 평가 파이프라인
│   ├── questions.json              # 50문항 (11개 유형)
│   ├── run_eval.py                 # 자동 채점 스크립트
│   └── results/                    # 실험별 결과 JSON
│
├── tests/                          # 단위·통합 테스트
├── docs/
│   ├── evaluation/EVALUATION.md   # 성능 평가 기록 (eval 실험 이력 포함)
│   └── dev-log/                   # 날짜별 개발 일지
│
└── .env.example                   # 환경변수 템플릿
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

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_REASONING_MODEL=gpt-4o
PG_PORT=5433
PG_HOST=localhost
```

### 2. DB 기동

```powershell
docker-compose up -d
python scripts/healthcheck.py
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
# 41/41 PASS
```

---

## LLM 품질 평가 (50문항 eval)

```powershell
# 서버 실행 후
python eval/run_eval.py --prefix my_test
```

결과: `eval/results/my_test_YYYYMMDD_HHMMSS.json`

| 문항 유형 | 수 |
|---|---|
| speaker_statement | 15 |
| unanswerable (할루시네이션 트랩) | 6 |
| comparison | 7 |
| date_based | 6 |
| speaker_confusion | 5 |
| multi_chunk / cause_effect 등 | 11 |

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| UI | React + Vite |
| API | FastAPI + uvicorn (SSE 스트리밍) |
| RAG 오케스트레이션 | LangGraph |
| LLM | GPT-4o-mini (일반) / GPT-4o (추론 필요) |
| 임베딩 | BAAI/bge-m3-unsupervised (1024차원, Dense+Sparse) |
| 벡터 DB | PostgreSQL + pgvector |
| Neural Reranker | BAAI/bge-reranker-v2-m3 |
| ETL | Python (pdfplumber, psycopg2) |
| 평가 | 자체 50문항 eval + RAGAS |
| 단위 테스트 | pytest |

---

## 주요 설계 결정

**발언자 단위 청킹**: 고정 길이 청킹 대신 `◯` 마커로 발언자 경계에서 분리. 한 발언자의 발언이 섞이지 않아 인용 정확도 향상.

**BGE-M3 하이브리드 검색**: Dense(의미 유사도) + Sparse(키워드) 점수를 함께 사용. 발언자명·날짜 포함 질문에서 단일 벡터 검색 대비 recall 향상.

**하이브리드 모델 라우팅**: 존재 여부 질문("~한 내용이 있나요?")은 gpt-4o로 전환 + 2단계 검증으로 허위 전제 거절. 일반 질문은 gpt-4o-mini 유지로 비용 절감.

**REFUSED 레벨**: 올바른 거절(할루시네이션 트랩 방어 성공)을 NONE(근거 부족)과 UI에서 명확히 구분.

**SSE 스트리밍**: `/query/stream` 엔드포인트로 토큰 단위 실시간 출력. 체감 응답속도 향상.

---

## 문서 맵

| 문서 | 내용 |
|------|------|
| [docs/evaluation/EVALUATION.md](docs/evaluation/EVALUATION.md) | 검색 회귀·LLM eval·실험 이력 |
| [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | 설계 결정 근거 |
| [docs/dev-log/](docs/dev-log/) | 날짜별 개발 일지 |
| [CHANGELOG.md](CHANGELOG.md) | 완료 이력 |
