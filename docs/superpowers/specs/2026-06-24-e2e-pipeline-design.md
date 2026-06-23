---
title: E2E 파이프라인 통합 테스트 설계
date: 2026-06-24
status: approved
---

# E2E 파이프라인 통합 테스트 설계

## 목표

실제 PostgreSQL(pgvector) DB에 적재된 데이터를 기반으로
RAG 파이프라인 전체(DB 상태 확인 → Search → Generate)를 1회 실행하여 검증한다.

ETL 단계(parser/normalizer/chunker)는 단위 테스트 41개가 이미 커버하므로
이 E2E 테스트는 ETL 출력물의 계약(contract) 검증 + RAG 파이프라인 통합에 집중한다.

---

## 범위

```
[DB: chunks 5건] → [embeddings_e5 확인] → [Retriever.search] → [Generator.generate_with_citations]
```

- PDF 신규 적재 없음 — 기존 chunks/embeddings 데이터 재사용
- 실제 DB 연결 필요 (mock 없음)
- `PG_PORT=5433` 환경으로 분리된 테스트 DB 사용

---

## 파일 구조

```
tests/
  conftest.py          # --pg-port 옵션, DB 연결 픽스처 (신규)
  test_e2e_pipeline.py # E2E 테스트 본체 (신규)
```

---

## conftest.py 설계

### CLI 옵션
```
pytest --pg-port 5433
```
`--pg-port` 값을 `PG_PORT` 환경변수로 설정한 뒤 `DatabaseConfig.from_env()`가 읽도록 한다.

### 픽스처
| 픽스처 | 스코프 | 설명 |
|--------|--------|------|
| `pg_port` | session | `--pg-port` 값 반환 |
| `db_conn` | session | psycopg2 연결. 실패 시 `pytest.skip` |
| `sample_chunks` | session | `chunks` 테이블에서 5건 조회 결과 |

---

## test_e2e_pipeline.py 설계

### 클래스: `TestE2EPipeline`

| 메서드 | 검증 내용 | 실패 시 동작 |
|--------|-----------|-------------|
| `test_db_connection` | psycopg2 연결 성공, `chunks` 테이블 접근 가능 | skip (DB 없음) |
| `test_chunks_exist_and_schema` | chunks 1건 이상 존재, `chunk_id`/`text`/`metadata` 키 확인 | fail |
| `test_embeddings_exist_and_dimension` | `embeddings_e5` 레코드 존재, 벡터 차원 == 384 | fail |
| `test_search_returns_results` | `Retriever.search("한미동맹 논의", top_k=3)` → 결과 1건 이상, `content`/`chunk_id`/`hybrid_score` 포함 | fail |
| `test_generate_with_citations` | `Generator.generate_with_citations(질문, retrieved)` → 비어있지 않은 문자열 | fail |

### 실행 명령
```powershell
pytest tests/test_e2e_pipeline.py -v --pg-port 5433
```

---

## 의존성 처리

- `test_db_connection` 실패 → 나머지 테스트 자동 skip (`db_conn` 픽스처 의존)
- `test_chunks_exist_and_schema` 실패 → `test_search_returns_results` 이전에 조기 확인 가능
- `EmbeddingEncoder` 실제 로딩 — 이미 설치된 `multilingual-e5-small` 모델 사용
- `Generator.generate_with_citations` — OpenAI API 키 없는 경우 fallback 경로(요약 반환)로 검증

---

## 성공 기준

1. `pytest tests/test_e2e_pipeline.py -v --pg-port 5433` 실행 시 5개 테스트 전부 PASS
2. DB 미연결 환경에서는 `test_db_connection` 1개 SKIP, 나머지 4개도 SKIP (CI 안전)
3. 실행 시간 60초 이내
