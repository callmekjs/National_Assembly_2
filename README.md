# 국회 회의록 근거 기반 질의응답 (RAG)

> **메인 스토리: 회의록을 검색해 근거를 붙인 뒤 LLM으로 답하는 RAG.**  
> **전제 레이어: 그 검색을 가능하게 하는 데이터 파이프라인·벡터 DB.**

| 문서 | 내용 |
|------|------|
| [ROADMAP.md](ROADMAP.md) | 앞으로 무엇을 할 것인가? |
| [CHANGELOG.md](CHANGELOG.md) | 지금까지 무엇이 완성됐는가? |
| [EVALUATION.md](EVALUATION.md) | 성능이 좋다는 근거는 무엇인가? |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 왜 이렇게 설계했는가? |
| [docs/dev-log/](docs/dev-log/) | 개발 과정에서 구체적으로 무엇을 했는가? |

`회의록 질의`(Streamlit · LangGraph)는 **검색만으로는 끝나지 않으며**, 답변 생성 단계에서 **`OPENAI_API_KEY`가 `.env`에 있으면 OpenAI Chat API를 우선** 사용하고(`OPENAI_MODEL` 등), 없거나 실패 시 **로컬 HF**(`service/llm/llm_client.py`)로 폴백합니다. CLI `qa_demo`는 OpenAI 키 유무에 따라 경로가 다를 수 있습니다(본문 하단 참고).

---

## 이 프로젝트가 증명하는 것

> **공개 정책 데이터를 근거 기반 질의응답까지 연결하는 엔드투엔드 역량**

- **사용자 가치(LLM/RAG)**: 질문 → 회의록 검색 → **LLM 답변** → 출처 번호 **`[n]`** 및 인용 블록
- **데이터 기반(전제)**: 원문 수집·중복 방지 → Extract/Transform → 청킹·메타데이터 → Postgres·pgvector 적재로 **검색 품질** 확보

---

## 한마디로 뭘 하는 프로젝트인가?

**질문하면 회의록에서 근거를 찾아 LLM이 답하고**, 답변 끝에 **출처 인용**이 붙는 **RAG 앱**이 핵심입니다.

그 뒤에 깔리는 것이 **파이프라인**입니다.

**회의록 데이터 파이프라인(전제)**

`수집 → Extract → Transform(정규화·청킹) → Load(문서·벡터)`

→ 검색 가능한 상태를 만든 뒤, 위 RAG/UI가 동작합니다.

---

## 전체 구조

```text
[사용자·메인] Streamlit 회의록 질의 · LangGraph
   질문 → Retrieve(하이브리드·리랭크) → Generate(LLM) → 참고 자료 [n]

[전제·기반 데이터 파이프라인]

[원문 회의록]
   └─ incoming_data/

          ↓ Extract
   service/etl/extractor/extractor.py

          ↓ Transform
   service/etl/transform/parser.py
   service/etl/transform/normalizer.py
   service/etl/transform/chunker.py

          ↓ Load
   service/etl/loader/jsonl_to_postgres.py
   service/etl/loader/embeddings.py

          ↓
   Postgres + pgvector  →  service/rag/* , graph/*
```

---

## 파이프라인 단계

| 단계 | 하는 일 | 주요 산출물 |
|---|---|---|
| **Extract** | 원천 파일을 읽어 추출 데이터 생성 | `data/extract/extracted.jsonl` |
| **Transform** | 파싱/정규화/청킹 | `data/transform/final/chunks.jsonl` |
| **Load** | 문서 적재 + 임베딩 적재 | `chunks`, `embeddings_e5` 테이블 |
| **Retrieve** | 질의 임베딩 기반 top-k 검색 | 관련 청크 리스트 |
| **Generate** | 검색 근거 기반 답변 생성 | 요약/답변 텍스트 |

---

## 실행 방법

### 1) 환경 준비

```powershell
cd C:\National_Assembly_2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Extract

```powershell
python -m service.etl.extractor.extractor
```

### 3) Transform

```powershell
python -m service.etl.transform.pipeline
```

### 4) Load (스키마 생성 → 문서 적재 → 임베딩 적재)

```powershell
python -m service.etl.loader.loader_cli db create
python -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
python -m service.etl.loader.loader_cli load vector
```

### 5) Streamlit 실행

```powershell
streamlit run app.py
```

`회의록 질의` 페이지에서는 왼쪽 사이드바의 **검색·답변 설정**에서 위원회·top-k 등을 바꿀 수 있습니다.

### 6) 원클릭 파이프라인 실행(권장)

```powershell
.\run_pipeline.ps1 -PgPort 5433
```

재실행 검증(문서·벡터 적재 2회 연속):

```powershell
.\run_pipeline.ps1 -PgPort 5433 -SkipCrawl -VerifyIdempotent
```

운영 복구 절차 요약은 `OPERATIONS.md`를 참고합니다.

### 7) 검색 + 답변(근거 인용) CLI 데모

```powershell
.\run_qa_demo.ps1 -Query "대북정책 핵심 쟁점은?" -Committee "외교통일위원회" -TopK 5 -PgPort 5433
```

출력 형식:
- 상단: 답변(요약)
- 하단: 근거 목록(`[1] source=... date=... quote=...`)

### v1 마감 검증 (Day 10, 팀 재현용)

아래는 DB가 기동되고 `chunks`/`embeddings_e5`가 채워져 있다는 가정입니다.

1. **Retrieval 회귀 평가**

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PG_PORT='5433'
.\.venv\Scripts\python.exe -m service.rag.evaluate_retrieval --pg-port 5433
```

- 평가셋 기본 파일: `service/rag/eval_queries_fixed.json`
- 플래그 기본값: `top_k=3`, `alpha=0.8`, 후보 배수(`candidate-multiplier`) 50 등은 `evaluate_retrieval` 및 Streamlit 검색 노드와 맞춤
- 회귀 기록: `service/rag/eval_report_day11.json` (옵션: `--report-out …`)
- (선택) 위원회·리랭커까지 켠 비교 실행: README 하단 qa_demo 또는 `--committee`, `--use-reranker` 등으로 재현 가능
- Streamlit과 동일한 메타에서 **참고 자료·청크 번호 정합**(Day 11):  
  `python -m service.rag.verify_streamlit_citation_alignment --pg-port 5433`

2. **QA CLI 데모 3문항**

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PG_PORT='5433'
.\.venv\Scripts\python.exe -m service.rag.qa_demo --query "외교통일위원회 회의록에서 대북정책 핵심 쟁점을 요약해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
.\.venv\Scripts\python.exe -m service.rag.qa_demo --query "외교부장관과 위원 질의자의 입장 차이를 근거와 함께 설명해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
.\.venv\Scripts\python.exe -m service.rag.qa_demo --query "정보 공유 제한 이슈가 언급된 회의가 있나?" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
```

각 실행에서 `Search hits: 5` 및 답변 하단 `근거:` 블록의 `[n] source=… date=… quote=…` 형식을 확인합니다.

3. **Streamlit 데모**

```powershell
streamlit run app.py
```

- 사이드바 **회의록 질의** → 질문 입력 → 답변 및 맨 아래 **참고 자료** 블록 확인
- 사이드바 **검색·답변 설정**에서 위원회·top-k 조정 가능

자세한 장애 대응은 `OPERATIONS.md`를 참고합니다.

### v0 실행 순서 (5줄)

```powershell
docker-compose up -d
.\.venv\Scripts\python.exe -m service.etl.extractor.extractor
.\.venv\Scripts\python.exe -m service.etl.transform.pipeline
.\.venv\Scripts\python.exe -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final; .\.venv\Scripts\python.exe -m service.etl.loader.loader_cli load vector
.\.venv\Scripts\python.exe -m service.rag.qa_demo --query "대북정책 핵심 쟁점을 요약해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
```

### 필수 환경변수/포트

- `PG_PORT=5433` (이 프로젝트 DB 컨테이너 포트; 로컬 Postgres와 충돌 시 반드시 분리)
- 기본 DB 접속값: `PG_HOST=localhost`, `PG_DB=skn_project`, `PG_USER=postgres`, `PG_PASSWORD=post1234`
- **Streamlit / LangGraph 질의**: `.env`에 **`OPENAI_API_KEY`**`(+, OPENAI_MODEL·OPENAI_BASE_URL)`이 있으면 API로 생성. 키가 없거나 **`FORCE_LOCAL_LLM=1`**이면 로컬 HF 경로(`MODEL_DIR_BASE`, `MODEL_DIR_ADAPTER` 등) 필요. OpenAI 오류 후 로컬도 실패하면 안내 메시지만 나옵니다(`OPENAI_ONLY=1`이면 폴백 안 함).
- **CLI `qa_demo`**: `OPENAI_API_KEY`가 있으면 OpenAI 호출, 없으면 근거 요약 폴백으로 동작합니다.
- Windows PowerShell에서 유니코드 출력 오류가 나면 실행 전에 `$env:PYTHONIOENCODING='utf-8'` 설정을 권장합니다.

### 자주 나는 오류와 해결 (Top 3)

1. `ModuleNotFoundError: No module named 'rag'`
   - 해결: `python -m service.rag...` 형태로 실행 (`rag` 대신 `service.rag`)
2. `relation "embeddings_e5" does not exist`
   - 해결: `db create` + `load doc` + `load vector` 순서로 재실행
3. `connection ... port 5432 failed`
   - 해결: 다른 로컬 Postgres와 충돌 가능성 높음, `PG_PORT=5433`로 고정

---

## 프로젝트 구조

```text
National_Assembly_2/
├── app.py
├── pages/
├── service/
│   ├── etl/
│   │   ├── extractor/
│   │   ├── transform/
│   │   └── loader/
│   ├── llm/
│   └── rag/
├── graph/
├── config/
└── requirements.txt
```

---

## 기술 스택

| 계층 | 기술 |
|---|---|
| **질의·생성 (메인)** | LangGraph, **로컬 LLM**(Hugging Face / `service/llm`) |
| UI | Streamlit |
| 검색·RAG | sentence-transformers (E5), 하이브리드·리랭크 (`service/rag`) |
| ETL·전제 | Python, Postgres 적재 파이프라인 |
| 벡터 저장 | PostgreSQL, pgvector |

---

## 벤치마킹 포인트 (적용/권장)

아래 항목은 실무형 파이프라인 품질을 높이기 위해 벤치마킹할 가치가 있습니다.

1. **Run ID 기반 실행 추적**
   - 실행마다 `run_id`를 발급해 입력/출력/로그를 묶어 관리
   - 재현성 및 디버깅 속도 개선

2. **Replay 가능한 파이프라인 실행**
   - 같은 입력과 설정으로 재실행 가능한 구조
   - 회귀 테스트 및 품질 검증 자동화에 유리

3. **스키마 계약(Contract) 강제**
   - Extract/Transform/Load 경계마다 필수 필드 검증
   - 누락/오염 데이터 조기 차단

4. **QA Rule Engine 고도화**
   - 길이, 날짜 형식, 중복, 파싱 실패율 등 규칙 점수화
   - `good/review/bad` 등급 분류 및 재처리 큐 운영

5. **데이터셋/실험 분리**
   - 운영 데이터와 평가 데이터셋을 분리 관리
   - 모델/검색 성능 비교 실험 체계화

6. **검색 단계 하이브리드화**
   - 벡터 검색 + 키워드(BM25) 결합 및 리랭크 도입
   - 정책 질의의 재현율/정밀도 동시 개선

---

## 현재 상태와 다음 단계

### 현재 상태 (v1)
- **제품 UX**: LangGraph 기반 회의록 질의(UI)에서 **LLM 생성 + 근거 인용**까지 일관 제공
- **전제 데이터**: ETL → 벡터 적재 → 하이브리드 검색·리랭크·평가(`eval_queries_fixed.json`, `evaluate_retrieval`)
- 인용 형식 고정 (`[n] source/date/quote`)
- 운영 가이드: `OPERATIONS.md`, 파이프라인 로그 표준 및 이중 재실행 검증(`run_pipeline.ps1 -VerifyIdempotent`)

### 다음 단계

[ROADMAP.md](ROADMAP.md) 참고 — Day 14~15 배포·발표, 멀티턴, FastAPI, 데이터 확장 등.

---

## 한 줄 요약

> 국회 회의록으로 **근거 기반 LLM 질의응답(RAG)** 을 제공하고, 그 검색을 뒷받침하는 **ETL·벡터 파이프라인**을 포함한 프로젝트입니다.