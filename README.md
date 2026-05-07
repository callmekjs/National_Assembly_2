# 국회 위원회 회의록 분석 파이프라인

> **국회 회의록 원문을 수집/정제/구조화해 검색과 요약에 활용할 수 있도록 만드는 데이터 파이프라인 프로젝트**

---

## 이 프로젝트가 증명하는 것

> **공개 정책 데이터를 서비스 가능한 데이터 자산으로 전환하는 역량**

국회 회의록은 공개되어 있지만, 원문 상태 그대로는 검색/요약/분석에 바로 쓰기 어렵습니다.  
본 프로젝트는 회의록 데이터를 ETL 파이프라인으로 정리해, 근거 기반 질의응답의 입력 데이터로 활용할 수 있도록 만듭니다.

- 원문 파일 수집 후 중복/누락 여부 점검
- 텍스트 추출 및 정제
- 문서 메타데이터 표준화
- 발언/문단 단위 청킹
- 벡터 적재 및 검색 기반 질의응답 연결

---

## 한마디로 뭘 하는 프로젝트인가?

국회 회의록 데이터를

**수집(Extract) → 정제/정규화/청킹(Transform) → 벡터 적재(Load) → 검색/요약(RAG)**  

흐름으로 처리하여, 정책 쟁점을 빠르게 탐색할 수 있는 기반을 구축하는 프로젝트입니다.

---

## 전체 구조

```text
[원문 회의록]
   └─ incoming_data/

          ↓ 1. Extract
   service/etl/extractor/extractor.py

          ↓ 2. Transform
   service/etl/transform/parser.py
   service/etl/transform/normalizer.py
   service/etl/transform/chunker.py

          ↓ 3. Load
   service/etl/loader/jsonl_to_postgres.py
   service/etl/loader/embeddings.py

          ↓ 4. Search/QA
   service/rag/*
   graph/*
   app.py (Streamlit)
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

### 6) 원클릭 파이프라인 실행(권장)

```powershell
.\run_pipeline.ps1 -PgPort 5433
```

### 7) 검색 + 답변(근거 인용) CLI 데모

```powershell
.\run_qa_demo.ps1 -Query "대북정책 핵심 쟁점은?" -Committee "외교통일위원회" -TopK 5 -PgPort 5433
```

출력 형식:
- 상단: 답변(요약)
- 하단: 근거 목록(`[1] source=... date=... quote=...`)

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
| ETL | Python, pandas |
| 벡터 저장 | PostgreSQL, pgvector |
| 임베딩 | sentence-transformers (E5) |
| 오케스트레이션 | LangGraph |
| UI | Streamlit |

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

### 현재 상태
- 기본 ETL 파이프라인(Extract/Transform/Load)과 질의응답 흐름 연결 완료
- 단일 임베딩 모델(E5) 기준으로 구조 단순화 완료

### 다음 단계
- 회의록 PDF 전용 수집/추출 모듈 고도화
- 발언자 단위 분리 정확도 개선
- 검색/요약 평가셋 구축 및 자동 회귀 테스트 추가

---

## 한 줄 요약

> 국회 위원회 회의록 데이터를 서비스 가능한 형태로 변환해, 검색과 근거 기반 요약까지 연결하는 **정책 데이터 파이프라인** 프로젝트입니다.