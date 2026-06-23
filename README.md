# 국회 회의록 근거 기반 질의응답 시스템

> 외교통일위원회 회의록 55건을 벡터 DB에 적재하고,  
> 질문하면 관련 발언을 검색해 LLM이 **출처 인용과 함께** 답변하는 RAG 시스템.

---

## 핵심 수치 (2026-06-23 기준)

| 지표 | 수치 |
|------|------|
| 데이터 | 외교통일위원회 회의록 55건 |
| 청크 수 | 18,048개 (발언자 단위) |
| recall@3 | **100%** (10/10) |
| RAGAS faithfulness | **0.9857** |
| 할루시네이션 방어 | Grounding Check FULL / PARTIAL / NONE 3단계 |
| 시스템 테스트 | 22/22 PASS |
| 데이터 파이프라인 테스트 | 13/13 PASS |
| 단위 테스트 | **41/41 PASS** (chunker · normalizer · retriever) |
| API | FastAPI `POST /query` · `GET /meetings` · `GET /health` |

---

## 시스템 아키텍처

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  LangGraph 파이프라인                 │
│                                                     │
│  Query Rewrite → Retrieve → Rerank → Grounding     │
│                               Check → Generate     │
└─────────────────────────────────────────────────────┘
         │                  │
         ▼                  ▼
  ┌─────────────┐    ┌────────────────┐
  │  pgvector   │    │  BM25 검색     │
  │  벡터 검색   │    │  (키워드)      │
  └─────────────┘    └────────────────┘
         │                  │
         └────────┬─────────┘
                  ▼
         RRF Fusion 결합
                  │
                  ▼
         Neural Reranker
         (BAAI/bge-reranker-v2-m3)
                  │
                  ▼
         GPT-4o-mini 답변 생성
         + [n] 출처 인용
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
    service/etl/transform/chunker.py      # 발언자(◯) 단위 청킹
    → data/transform/final/chunks.jsonl  (18,048건)
    │
    ▼  Validate
    service/etl/contract.py               # 필수 필드 자동 검증
    service/etl/quality.py                # 품질 리포트 생성
    service/etl/run_tracker.py            # 실행 이력 저장
    │
    ▼  Load
    service/etl/loader/jsonl_to_postgres.py  → chunks 테이블
    service/etl/loader/embeddings.py         → embeddings_e5 테이블
    (multilingual-e5-small, 384차원, incremental)
```

**파이프라인 품질 보증**
- Contract: chunk_id·content 100% / speaker 98.6% / meeting_date 100%
- 중복 임베딩 0건 (incremental 방식)
- run_history.jsonl 로 실행 이력 추적

---

## RAG 파이프라인 (LangGraph 노드)

| 노드 | 역할 |
|------|------|
| `router` | 질문 유형 분류 (일반 / 비교 / 발언자 단독 / OOD) |
| `query_rewrite` | 질문 → LLM으로 검색 최적화 변형 |
| `retrieve_pg` | Fusion(BM25 + 벡터 RRF) + Neural Reranker |
| `grounding_check` | 검색 결과와 답변의 근거 수준 평가 (FULL / PARTIAL / NONE) |
| `generate` | GPT-4o-mini 답변 생성 + `[n]` 인용 번호 삽입 |
| `context_trim` | 토큰 초과 방지 컨텍스트 트리밍 |

**검색 전략 (사이드바에서 on/off)**
- Fusion Retrieval: BM25 + 벡터 검색 결과를 RRF로 통합 (기본 ON)
- Neural Reranker: cross-encoder로 질문-청크 점수 재계산 (기본 ON)
- Multi-query: 질문 변형 3개 생성 후 통합
- HyDE: 가상 답변 임베딩으로 검색
- 발언자 필터: 특정 발언자 단독 검색

---

## 프로젝트 구조

```
National_Assembly_2/
│
├── app.py                          # Streamlit 진입점
├── pages/
│   ├── page1.py                    # 회의록 질의 페이지 라우터
│   └── views/
│       └── chat.py                 # 채팅 UI (스트리밍·PDF 뷰어·참고자료 테이블)
│
├── graph/                          # LangGraph RAG 파이프라인
│   ├── app_graph.py                # 그래프 빌드 진입점
│   ├── state.py                    # GraphState 정의
│   └── nodes/
│       ├── router.py               # 질문 유형 라우터
│       ├── query_rewrite.py        # 질문 변형
│       ├── retrieve_pg.py          # Fusion + Neural Reranker 검색
│       ├── grounding_check.py      # 근거 수준 평가 (FULL/PARTIAL/NONE)
│       ├── generate.py             # LLM 답변 생성
│       └── context_trim.py         # 컨텍스트 트리밍
│
├── api/
│   └── main.py                     # FastAPI 앱 (POST /query, GET /meetings, GET /health, 모니터링 엔드포인트)
│
├── service/
│   ├── etl/                        # 데이터 파이프라인
│   │   ├── extractor/
│   │   │   └── extractor.py        # PDF → extracted.jsonl
│   │   ├── transform/
│   │   │   ├── normalizer.py       # 텍스트 정규화
│   │   │   ├── chunker.py          # 발언자 단위 청킹
│   │   │   └── pipeline.py         # Transform 전체 실행
│   │   ├── loader/
│   │   │   ├── jsonl_to_postgres.py # chunks 테이블 적재
│   │   │   └── embeddings.py        # 임베딩 적재 (incremental)
│   │   ├── contract.py             # 스키마 계약 검증
│   │   ├── quality.py              # 품질 리포트 생성
│   │   └── run_tracker.py          # 실행 이력 추적
│   │
│   ├── llm/
│   │   ├── llm_client.py           # OpenAI 우선 / 로컬 HF 폴백
│   │   └── prompt_templates.py     # 위원회 도메인 특화 프롬프트
│   │
│   ├── monitoring/
│   │   └── query_logger.py         # 쿼리 로그 DB 저장 · recall=0 감지 · latency 추적
│   │
│   └── rag/
│       ├── retrieval/
│       │   ├── retriever.py         # Retriever 통합 인터페이스
│       │   └── bm25_retriever.py    # BM25 키워드 검색
│       ├── vectorstore/
│       │   └── pgvector_store.py    # pgvector 벡터 검색
│       ├── models/
│       │   └── config.py            # 임베딩 모델 설정
│       └── eval/
│           ├── eval_dataset.json         # RAGAS 평가셋 50문항
│           ├── eval_dataset_manual.json  # 수동 평가셋 23문항
│           ├── ragas_eval.py             # RAGAS 자동 평가
│           └── unanswerable_eval.py      # OOD 거부 평가
│
├── tests/                          # 단위 테스트 (41/41 PASS, DB 없이 실행)
│   ├── test_chunker.py             # chunker 13개
│   ├── test_normalizer.py          # normalizer 16개
│   └── test_retriever.py           # retriever 내부 메서드 12개
│
├── docs/
│   ├── test.md                     # 시스템 테스트 명세 (22개)
│   ├── test_eval.md                # 시스템 테스트 결과 (22/22 PASS)
│   ├── Data_test.md                # 데이터 파이프라인 테스트 명세 (13개)
│   ├── Data_test_eval.md           # 데이터 테스트 결과 (13/13 PASS)
│   ├── architecture/
│   │   └── ARCHITECTURE.md         # 설계 결정 근거
│   ├── evaluation/
│   │   └── EVALUATION.md           # 성능 평가 기록
│   └── dev-log/                    # 날짜별 개발 일지
│
├── data/
│   ├── extract/extracted.jsonl     # ETL 중간 산출물
│   ├── transform/final/chunks.jsonl
│   └── reports/                    # quality 리포트 / RAGAS 결과
│
├── incoming_data/
│   └── 외교통일위원회/*.pdf         # 원본 회의록 (55건)
│
├── CHANGELOG.md                    # 완료 이력
├── ROADMAP.md                      # 앞으로 할 것
├── requirements.txt
└── run_pipeline.ps1                # 원클릭 파이프라인
```

---

## 서비스 구성

| 서비스   | 포트  | 볼륨           | 설명                       |
|---------|-------|----------------|----------------------------|
| postgres | 5432  | postgres_data  | PostgreSQL + pgvector DB   |
| (앱)     | 8501  | —              | Streamlit (로컬 직접 실행) |

> **포트 충돌 시** `.env`에서 `PG_PORT=5433`으로 변경 후 `docker-compose up -d` 재실행.

---

## 빠른 시작

### 1. 환경 준비

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env` 파일 생성:

```
OPENAI_API_KEY=sk-...
PG_PORT=5433
PG_HOST=localhost
PG_DB=skn_project
PG_USER=postgres
PG_PASSWORD=post1234
```

### 2. DB 기동 (PostgreSQL + pgvector)

```powershell
docker-compose up -d
```

DB 기동 후 정상 여부 확인:

```powershell
python scripts/healthcheck.py
```

정상 출력:
```
[✅] Postgres 연결 (localhost:5432/skn_project)
[✅] chunks 테이블: 18,048건
[✅] embeddings_e5 테이블: 17,xxx건
[✅] 벡터 차원: 384

모든 헬스 체크 통과 ✅
```

### 3. 데이터 파이프라인 실행

```powershell
# 원클릭 (권장)
.\run_pipeline.ps1 -PgPort 5433

# 단계별
python -m service.etl.extractor.extractor
python -m service.etl.transform.pipeline
python -m service.etl.loader.loader_cli db create
python -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
python -m service.etl.loader.loader_cli load vector
```

### 4. Streamlit 앱 실행

```powershell
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속 → 회의록 질의 페이지

### 5. FastAPI 서버 실행 (선택)

```powershell
uvicorn api.main:app --reload --port 8000
```

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /query` | 질문 → 답변 + 인용 + latency |
| `GET /meetings` | 적재된 회의 목록 |
| `GET /health` | DB 연결 + 청크 수 확인 |
| `GET /logs` | 최근 쿼리 로그 |
| `GET /logs/failures` | recall=0 질의 목록 |
| `GET /logs/stats` | grounding 분포 · 평균 latency |
| `GET /docs` | Swagger UI (자동 생성) |

### 6. 단위 테스트 실행

```powershell
pytest tests/ -v
# 41/41 PASS (DB 불필요)
```

---

## 평가 실행

### RAGAS 자동 평가

```powershell
python -m service.rag.eval.ragas_eval --limit 10
```

| 지표 | 점수 |
|------|------|
| faithfulness | 0.9857 |
| context_precision | 측정 완료 |

### OOD 거부 평가

```powershell
python -m service.rag.eval.unanswerable_eval --pg-port 5433
```

회의록과 무관한 질문(AI, 스포츠, 타 위원회 등)에 80% 이상 거부 응답 확인.

### 검색 품질 평가

```powershell
python -m service.rag.evaluate_retrieval --pg-port 5433
```

recall@3: 100% (10/10)

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| UI | Streamlit |
| API | FastAPI + uvicorn |
| RAG 오케스트레이션 | LangGraph |
| LLM | OpenAI GPT-4o-mini (로컬 HF 폴백) |
| 임베딩 | multilingual-e5-small (384차원) |
| 벡터 DB | PostgreSQL + pgvector (port 5433) |
| 키워드 검색 | BM25 (rank_bm25) |
| Neural Reranker | BAAI/bge-reranker-v2-m3 |
| ETL | Python (pdfplumber, psycopg2) |
| 평가 | RAGAS 0.4.x |
| 단위 테스트 | pytest + pytest-mock |

---

## 주요 설계 결정

**발언자 단위 청킹**: 고정 길이 청킹 대신 `◯` 마커로 발언자 경계에서 분리. 한 발언자의 발언이 섞이지 않아 인용 정확도 향상. 단, 짧은 발언이 많아 300자 미만 청크 비율 69.9% (국회 발언 특성상 허용).

**Grounding Check**: LLM 답변 전에 검색 결과와 답변의 연관성을 FULL / PARTIAL / NONE으로 평가. NONE이면 "관련 내용을 찾지 못했습니다"로 거부 — 할루시네이션 방어 핵심.

**Fusion + RRF**: 벡터 검색(의미 유사도)과 BM25(키워드 정확도)를 Reciprocal Rank Fusion으로 결합. 단일 벡터 검색 대비 발언자명·날짜 포함 질문에서 recall 향상.

---

## 자주 나는 오류

| 오류 | 해결 |
|------|------|
| `relation "embeddings_e5" does not exist` | `loader_cli db create` → `load doc` → `load vector` 순서로 재실행 |
| `connection ... port 5432 failed` | `.env`에 `PG_PORT=5433` 확인 |
| `ModuleNotFoundError: No module named 'rag'` | `python -m service.rag...` 형태로 실행 |
| Windows 유니코드 오류 | `$env:PYTHONIOENCODING='utf-8'` 설정 후 재실행 |

---

## 문서 맵

| 문서 | 내용 |
|------|------|
| [CHANGELOG.md](CHANGELOG.md) | 날짜별 완료 이력 |
| [ROADMAP.md](ROADMAP.md) | Day 14~15 남은 작업 |
| [docs/test_eval.md](docs/test_eval.md) | 시스템 테스트 22/22 PASS 결과 |
| [docs/Data_test_eval.md](docs/Data_test_eval.md) | 데이터 파이프라인 테스트 결과 |
| [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | 설계 결정 근거 |
| [docs/evaluation/EVALUATION.md](docs/evaluation/EVALUATION.md) | 성능 평가 기록 |
| [docs/dev-log/](docs/dev-log/) | 날짜별 개발 일지 |
