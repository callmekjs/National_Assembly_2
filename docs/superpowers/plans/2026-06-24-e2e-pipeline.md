# E2E 파이프라인 통합 테스트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실제 PostgreSQL DB의 기존 데이터를 사용해 DB 계약 검증 → Retriever.search → Generator.generate_with_citations 전 과정을 pytest로 검증한다.

**Architecture:** `tests/conftest.py`가 `--pg-port` CLI 옵션을 받아 환경변수를 설정하고 psycopg2 연결 픽스처를 제공한다. `tests/test_e2e_pipeline.py`는 이 픽스처에 의존해 5단계 E2E를 순서대로 검증한다. DB 미연결 환경에서는 전 테스트가 자동 skip된다.

**Tech Stack:** pytest, psycopg2, pgvector, multilingual-e5-small (intfloat/multilingual-e5-small)

## Global Constraints

- Python 3.10+, pytest 7+
- 테스트 DB 포트: `--pg-port 5433` (기본값 5432)
- DB: host=localhost, database=skn_project, user=postgres, password=post1234
- `EmbeddingEncoder` 실제 로딩 (mock 없음)
- 벡터 차원: 384 (multilingual-e5-small)
- `Retriever`, `Generator` 임포트는 반드시 테스트 함수 내부에서 수행 (모듈 레벨 임포트 금지 — 전역 DB 설정이 픽스처 실행 후 갱신되어야 함)

---

## File Map

| 파일 | 상태 | 역할 |
|------|------|------|
| `tests/conftest.py` | 신규 | `--pg-port` 옵션, `db_conn`/`sample_chunks` 세션 픽스처 |
| `tests/test_e2e_pipeline.py` | 신규 | E2E 5단계 테스트 클래스 |

---

### Task 1: conftest.py — pytest 옵션 및 DB 픽스처

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Produces:
  - `pg_port` fixture (session) → `int` — `PG_PORT` 환경변수 설정 후 포트 반환
  - `db_conn` fixture (session) → `psycopg2.connection` — 실패 시 `pytest.skip`
  - `sample_chunks` fixture (session) → `list[tuple[str, str, dict]]` — `(chunk_id, text, metadata)` 5건

- [ ] **Step 1: conftest.py 작성**

`tests/conftest.py` 전체 내용:

```python
import os
import sys
from pathlib import Path

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_addoption(parser):
    parser.addoption("--pg-port", action="store", default="5432", help="PostgreSQL port for E2E tests")


@pytest.fixture(scope="session")
def pg_port(request):
    port = int(request.config.getoption("--pg-port"))
    os.environ["PG_PORT"] = str(port)
    from config.vector_database import DatabaseConfig, update_db_config
    update_db_config(DatabaseConfig.from_env())
    return port


@pytest.fixture(scope="session")
def db_conn(pg_port):
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=pg_port,
            database="skn_project",
            user="postgres",
            password="post1234",
        )
    except Exception as exc:
        pytest.skip(f"DB 연결 실패 (PG_PORT={pg_port}): {exc}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def sample_chunks(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT chunk_id, text, metadata FROM chunks LIMIT 5")
        rows = cur.fetchall()
    return rows
```

- [ ] **Step 2: 컬렉션 확인 (테스트 없어도 import 오류 없어야 함)**

```powershell
cd C:\National_Assembly_2
pytest tests/conftest.py --collect-only --pg-port 5433
```

Expected: `no tests ran` 또는 수집 0건 (오류 없음)

- [ ] **Step 3: 커밋**

```bash
git add tests/conftest.py
git commit -m "test: E2E conftest — --pg-port 옵션 및 DB 픽스처 추가"
```

---

### Task 2: test_e2e_pipeline.py — 5단계 E2E 테스트

**Files:**
- Create: `tests/test_e2e_pipeline.py`

**Interfaces:**
- Consumes:
  - `db_conn` fixture → `psycopg2.connection`
  - `sample_chunks` fixture → `list[tuple[str, str, dict]]`
  - `pg_port` fixture → `int`
  - `Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL).search(query, top_k)` → `list[dict]`
  - `Generator().generate_with_citations(question, retrieved)` → `str`

- [ ] **Step 1: test_e2e_pipeline.py 작성**

`tests/test_e2e_pipeline.py` 전체 내용:

```python
"""
RAG 파이프라인 E2E 통합 테스트 (실제 DB 필요)

실행:
  pytest tests/test_e2e_pipeline.py -v --pg-port 5433
"""
import sys
from pathlib import Path

import psycopg2.extras
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestE2EPipeline:

    def test_db_connection(self, db_conn):
        """DB 연결 및 chunks 테이블 접근 가능 확인."""
        assert db_conn.closed == 0
        with db_conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1

    def test_chunks_exist_and_schema(self, sample_chunks):
        """chunks 테이블에 데이터가 있고 스키마 계약을 만족하는지 확인."""
        assert len(sample_chunks) >= 1, "chunks 테이블에 데이터가 없습니다"
        chunk_id, text, metadata = sample_chunks[0]
        assert chunk_id, "chunk_id가 비어있습니다"
        assert text, "text가 비어있습니다"
        assert isinstance(metadata, dict), f"metadata가 dict가 아닙니다: {type(metadata)}"

    def test_embeddings_exist_and_dimension(self, db_conn, sample_chunks):
        """embeddings_e5 테이블에 레코드가 있고 벡터 차원이 384인지 확인."""
        chunk_ids = [row[0] for row in sample_chunks]
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, embedding FROM embeddings_e5 WHERE chunk_id = ANY(%s) LIMIT 1",
                (chunk_ids,),
            )
            row = cur.fetchone()
        assert row is not None, "embeddings_e5에 해당 chunk_id 레코드가 없습니다"
        embedding = list(row[1])
        assert len(embedding) == 384, f"벡터 차원 불일치: {len(embedding)} (기대값 384)"

    def test_search_returns_results(self, pg_port):
        """Retriever.search가 실제 DB에서 결과를 반환하는지 확인."""
        from service.rag.retrieval.retriever import Retriever
        from service.rag.models.config import EmbeddingModelType

        retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
        results = retriever.search("한미동맹 논의", top_k=3)

        assert len(results) >= 1, "검색 결과가 없습니다"
        first = results[0]
        assert "content" in first, "결과에 'content' 키가 없습니다"
        assert "chunk_id" in first, "결과에 'chunk_id' 키가 없습니다"
        assert "hybrid_score" in first, "결과에 'hybrid_score' 키가 없습니다"
        assert isinstance(first["hybrid_score"], float), "hybrid_score가 float이 아닙니다"

    def test_generate_with_citations(self, pg_port):
        """Generator.generate_with_citations가 비어있지 않은 답변을 반환하는지 확인."""
        from service.rag.retrieval.retriever import Retriever
        from service.rag.models.config import EmbeddingModelType
        from service.rag.generation.generator import Generator

        retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
        retrieved = retriever.search("한미동맹에 대한 최근 논의", top_k=3)

        generator = Generator()
        answer = generator.generate_with_citations("한미동맹에 대한 최근 논의는?", retrieved)

        assert answer, "답변이 비어있습니다"
        assert len(answer) > 10, f"답변이 너무 짧습니다: '{answer}'"
```

- [ ] **Step 2: 전체 E2E 테스트 실행**

```powershell
cd C:\National_Assembly_2
pytest tests/test_e2e_pipeline.py -v --pg-port 5433
```

Expected 출력 (5개 모두 PASSED):
```
tests/test_e2e_pipeline.py::TestE2EPipeline::test_db_connection PASSED
tests/test_e2e_pipeline.py::TestE2EPipeline::test_chunks_exist_and_schema PASSED
tests/test_e2e_pipeline.py::TestE2EPipeline::test_embeddings_exist_and_dimension PASSED
tests/test_e2e_pipeline.py::TestE2EPipeline::test_search_returns_results PASSED
tests/test_e2e_pipeline.py::TestE2EPipeline::test_generate_with_citations PASSED
```

- [ ] **Step 3: DB 없는 환경에서 skip 동작 확인 (선택)**

```powershell
pytest tests/test_e2e_pipeline.py -v --pg-port 9999
```

Expected: 전 테스트 SKIPPED (`DB 연결 실패` 메시지 포함)

- [ ] **Step 4: 기존 단위 테스트 회귀 확인**

```powershell
pytest tests/test_normalizer.py tests/test_chunker.py tests/test_retriever.py -v
```

Expected: 전부 PASSED (회귀 없음)

- [ ] **Step 5: 커밋**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: E2E 파이프라인 통합 테스트 추가 (DB→Search→Generate)"
```
