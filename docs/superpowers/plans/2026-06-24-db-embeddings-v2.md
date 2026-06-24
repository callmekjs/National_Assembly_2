# 데이터 파이프라인 DB + Embeddings v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan A(ETL v2) 산출물 `chunks_v2.jsonl`을 PostgreSQL `chunks_v2` 테이블에 적재하고, `embed_text` 필드를 임베딩해 `embeddings_e5_v2` 테이블에 저장한다.

**Architecture:** schema_v2.sql → jsonl_to_postgres_v2.py → embeddings_v2.py 3단계 순차 실행. v1 테이블(`chunks`, `embeddings_e5`)은 건드리지 않는다. DB-touching 코드의 pure function은 완전히 분리해 단위 테스트 가능하게 설계.

**Tech Stack:** psycopg2, pgvector, multilingual-e5-small, PostgreSQL FTS (tsvector), pytest

## Global Constraints

- v1 파일(`schema_jsonl.sql`, `jsonl_to_postgres.py`, `embeddings.py`, `pgvector_store.py`) 수정 금지
- `ensure_ascii=False` 는 이 플랜에서는 JSON 직렬화가 없으므로 해당 없음
- `embed_text` 만 임베딩 — `raw_text`/`clean_text`는 임베딩 금지
- 임베딩 대상: `section_type = 'body'` 청크만
- `embeddings_e5_v2` 차원: `vector(384)` (v1과 동일 모델 multilingual-e5-small)
- `chunks_v2` INSERT 필드 순서: `chunk_id, source_id, page_no, turn_index, section_type, speaker, speaker_role, raw_text, clean_text, embed_text, metadata`
- `_parse_db_row` 반환 dict 키: `"embed_text"` (v1 `"natural_text"` 아님)
- `ROOT = Path(__file__).resolve().parents[3]` (모든 v2 파일 동일)
- 입력: `data/v2/transform/final/chunks_v2.jsonl` (Plan A Task 4 산출물)

---

## File Map

| 파일 | 상태 | 역할 |
|------|------|------|
| `service/etl/loader/schema_v2.sql` | 신규 | chunks_v2 + embeddings_e5_v2 DDL + 인덱스 |
| `service/etl/loader/jsonl_to_postgres_v2.py` | 신규 | chunks_v2.jsonl → chunks_v2 upsert |
| `service/etl/loader/embeddings_v2.py` | 신규 | chunks_v2.embed_text → embeddings_e5_v2 |
| `tests/test_jsonl_to_postgres_v2.py` | 신규 | _row_to_tuple + SQL 구조 단위 테스트 |
| `tests/test_embeddings_v2.py` | 신규 | _parse_db_row + _build_sql 순수 함수 단위 테스트 |

---

### Task 1: schema_v2.sql — DDL 작성

**Files:**
- Create: `service/etl/loader/schema_v2.sql`

**Interfaces:**
- Produces: PostgreSQL 실행 가능한 DDL. 이 스키마를 기반으로 Task 2, 3가 INSERT/SELECT한다.
- 테이블: `chunks_v2`, `embeddings_e5_v2`
- 인덱스: `idx_chunks_v2_source_id`, `idx_chunks_v2_committee`, `idx_chunks_v2_meeting_date`, `idx_chunks_v2_speaker`, `idx_chunks_v2_section_type`, `idx_chunks_v2_fts`

> Task 1은 DDL 파일이므로 단위 테스트가 없다. 커밋 후 DB가 있는 환경에서 `psql -f schema_v2.sql` 로 확인.

- [ ] **Step 1: schema_v2.sql 작성**

`service/etl/loader/schema_v2.sql` 전체 내용:

```sql
-- Plan B: v2 스키마. v1 테이블(chunks, embeddings_e5)은 건드리지 않는다.

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────
-- chunks_v2: ETL v2 청크 (raw_text / clean_text / embed_text 분리)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks_v2 (
    id          SERIAL PRIMARY KEY,
    chunk_id    VARCHAR(255) UNIQUE NOT NULL,
    source_id   VARCHAR(255),
    page_no     INTEGER,
    turn_index  INTEGER,
    section_type VARCHAR(20),
    speaker     VARCHAR(255),
    speaker_role VARCHAR(100),
    raw_text    TEXT NOT NULL,
    clean_text  TEXT NOT NULL,
    embed_text  TEXT NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 기본 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_chunks_v2_source_id
    ON chunks_v2(source_id);

-- metadata 내부 필드 인덱스 (위원회 필터링)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_committee
    ON chunks_v2 ((metadata->>'committee'));

-- metadata 내부 필드 인덱스 (날짜 필터링)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_meeting_date
    ON chunks_v2 ((metadata->>'meeting_date'));

-- 발언자 필터링
CREATE INDEX IF NOT EXISTS idx_chunks_v2_speaker
    ON chunks_v2(speaker);

-- section_type 필터링 (body만 임베딩/검색)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_section_type
    ON chunks_v2(section_type);

-- PostgreSQL FTS (한국어 기본 설정 simple 사용)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_fts
    ON chunks_v2 USING gin(to_tsvector('simple', clean_text));

-- ─────────────────────────────────────────────────────────────
-- embeddings_e5_v2: embed_text 기반 임베딩 (section_type=body만)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embeddings_e5_v2 (
    id          SERIAL PRIMARY KEY,
    chunk_id    VARCHAR(255) REFERENCES chunks_v2(chunk_id) ON DELETE CASCADE,
    embedding   vector(384) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_e5_v2_chunk_id
    ON embeddings_e5_v2(chunk_id);

-- pgvector HNSW 인덱스 (cosine distance, 검색 속도 향상)
-- 주의: 데이터 적재 완료 후 실행할 것 (적재 중 HNSW는 느림)
-- CREATE INDEX idx_embeddings_e5_v2_hnsw
--     ON embeddings_e5_v2 USING hnsw (embedding vector_cosine_ops);
```

- [ ] **Step 2: 커밋**

```bash
git add service/etl/loader/schema_v2.sql
git commit -m "feat: schema_v2 — chunks_v2 + embeddings_e5_v2 DDL + FTS + 인덱스"
```

---

### Task 2: jsonl_to_postgres_v2.py — chunks_v2 적재

**Files:**
- Create: `service/etl/loader/jsonl_to_postgres_v2.py`
- Create: `tests/test_jsonl_to_postgres_v2.py`

**Interfaces:**
- Consumes: `data/v2/transform/final/chunks_v2.jsonl` (Plan A Task 4 산출물)
- Produces: `chunks_v2` 테이블에 upsert
- `_connect() -> psycopg2.extensions.connection` — v1과 동일한 환경변수 패턴
- `_row_to_tuple(row: dict) -> tuple` — JSONL 레코드 → DB INSERT 튜플 (11개 값)
- `load_chunks_v2(jsonl_path: Path, batch_size: int = 1000) -> bool`

- [ ] **Step 1: 테스트 작성**

`tests/test_jsonl_to_postgres_v2.py` 전체 내용:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.loader.jsonl_to_postgres_v2 import _row_to_tuple, INSERT_SQL


def _sample_row() -> dict:
    return {
        "chunk_id": "20240717_52128_turn_0084",
        "source_id": "20240717_52128",
        "page_no": 12,
        "turn_index": 84,
        "section_type": "body",
        "speaker": "권칠승",
        "speaker_role": "위원",
        "raw_text": "원문 텍스트입니다.",
        "clean_text": "정제된 텍스트입니다.",
        "embed_text": "[회의일: 2024-07-17] [위원회: 외교통일위원회] [발언자: 권칠승 위원]\n정제된 텍스트입니다.",
        "metadata": {"committee": "외교통일위원회", "meeting_date": "2024-07-17"},
    }


def test_row_to_tuple_length():
    tup = _row_to_tuple(_sample_row())
    assert len(tup) == 11


def test_row_to_tuple_chunk_id():
    assert _row_to_tuple(_sample_row())[0] == "20240717_52128_turn_0084"


def test_row_to_tuple_source_id():
    assert _row_to_tuple(_sample_row())[1] == "20240717_52128"


def test_row_to_tuple_page_no_int():
    assert _row_to_tuple(_sample_row())[2] == 12


def test_row_to_tuple_turn_index_int():
    assert _row_to_tuple(_sample_row())[3] == 84


def test_row_to_tuple_section_type():
    assert _row_to_tuple(_sample_row())[4] == "body"


def test_row_to_tuple_embed_text_position():
    tup = _row_to_tuple(_sample_row())
    assert "[회의일: 2024-07-17]" in tup[9]


def test_row_to_tuple_metadata_is_dict():
    tup = _row_to_tuple(_sample_row())
    meta = tup[10]
    assert isinstance(meta.adapted, dict)
    assert meta.adapted["committee"] == "외교통일위원회"


def test_row_to_tuple_defaults_for_missing_fields():
    row = {"chunk_id": "cid", "raw_text": "r", "clean_text": "c", "embed_text": "e"}
    tup = _row_to_tuple(row)
    assert tup[1] == ""   # source_id
    assert tup[2] is None  # page_no
    assert tup[3] is None  # turn_index
    assert tup[4] == ""   # section_type


def test_insert_sql_targets_chunks_v2():
    assert "chunks_v2" in INSERT_SQL
    assert "chunks" not in INSERT_SQL.replace("chunks_v2", "")


def test_insert_sql_has_on_conflict():
    assert "ON CONFLICT (chunk_id) DO UPDATE" in INSERT_SQL
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
cd C:\National_Assembly_2
pytest tests/test_jsonl_to_postgres_v2.py -v
```

Expected: `ImportError` (파일 없음)

- [ ] **Step 3: jsonl_to_postgres_v2.py 작성**

`service/etl/loader/jsonl_to_postgres_v2.py` 전체 내용:

```python
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSONL = ROOT / "data" / "v2" / "transform" / "final" / "chunks_v2.jsonl"

INSERT_SQL = """
INSERT INTO chunks_v2
    (chunk_id, source_id, page_no, turn_index, section_type,
     speaker, speaker_role, raw_text, clean_text, embed_text, metadata)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (chunk_id) DO UPDATE
SET
    source_id    = EXCLUDED.source_id,
    page_no      = EXCLUDED.page_no,
    turn_index   = EXCLUDED.turn_index,
    section_type = EXCLUDED.section_type,
    speaker      = EXCLUDED.speaker,
    speaker_role = EXCLUDED.speaker_role,
    raw_text     = EXCLUDED.raw_text,
    clean_text   = EXCLUDED.clean_text,
    embed_text   = EXCLUDED.embed_text,
    metadata     = EXCLUDED.metadata
"""


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )


def _row_to_tuple(row: dict) -> tuple:
    return (
        row.get("chunk_id", ""),
        row.get("source_id", ""),
        row.get("page_no"),
        row.get("turn_index"),
        row.get("section_type", ""),
        row.get("speaker", ""),
        row.get("speaker_role", ""),
        row.get("raw_text", ""),
        row.get("clean_text", ""),
        row.get("embed_text", ""),
        Json(row.get("metadata", {})),
    )


def load_chunks_v2(jsonl_path: Path | None = None, batch_size: int = 1000) -> bool:
    path = Path(jsonl_path) if jsonl_path else DEFAULT_JSONL
    if not path.exists():
        print(f"[loader_v2] 파일 없음: {path}")
        return False

    conn = _connect()
    conn.autocommit = False
    total = 0
    try:
        with conn.cursor() as cur:
            rows: list[tuple] = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rows.append(_row_to_tuple(json.loads(line)))
                    if len(rows) >= batch_size:
                        cur.executemany(INSERT_SQL, rows)
                        total += len(rows)
                        rows.clear()
            if rows:
                cur.executemany(INSERT_SQL, rows)
                total += len(rows)
        conn.commit()
        print(f"[loader_v2] upsert_rows={total} → chunks_v2")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[loader_v2] ERROR: {e}")
        return False
    finally:
        conn.close()


def main() -> None:
    load_chunks_v2()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_jsonl_to_postgres_v2.py -v
```

Expected: `11 passed`

- [ ] **Step 5: 커밋**

```bash
git add service/etl/loader/jsonl_to_postgres_v2.py tests/test_jsonl_to_postgres_v2.py
git commit -m "feat: jsonl_to_postgres_v2 — chunks_v2 JSONL 적재 + 단위 테스트"
```

---

### Task 3: embeddings_v2.py — embed_text 임베딩

**Files:**
- Create: `service/etl/loader/embeddings_v2.py`
- Create: `tests/test_embeddings_v2.py`

**Interfaces:**
- Consumes: `chunks_v2` 테이블 (DB, `section_type='body'`)
- Produces: `embeddings_e5_v2` 테이블 upsert
- `_parse_db_row(row: tuple) -> dict` — `(id, chunk_id, embed_text)` → `{"id": int, "chunk_id": str, "embed_text": str}`
- `_build_count_sql(skip_existing: bool) -> str` — 임베딩 대상 카운트 SQL
- `_build_iter_sql(skip_existing: bool, limit: int | None) -> str` — 임베딩 대상 이터레이션 SQL
- `run(limit, batch_size, force) -> dict` — `{"embedded": int, "skipped": int}`

- [ ] **Step 1: 테스트 작성**

`tests/test_embeddings_v2.py` 전체 내용:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.loader.embeddings_v2 import (
    _parse_db_row,
    _build_count_sql,
    _build_iter_sql,
)


def test_parse_db_row_all_fields():
    row = (42, "20240717_52128_turn_0084", "[회의일: 2024-07-17]\n발언 내용")
    result = _parse_db_row(row)
    assert result["id"] == 42
    assert result["chunk_id"] == "20240717_52128_turn_0084"
    assert result["embed_text"] == "[회의일: 2024-07-17]\n발언 내용"


def test_parse_db_row_key_is_embed_text_not_natural_text():
    row = (1, "cid", "embed content")
    result = _parse_db_row(row)
    assert "embed_text" in result
    assert "natural_text" not in result


def test_parse_db_row_empty_embed_text():
    row = (1, "cid", "")
    assert _parse_db_row(row)["embed_text"] == ""


def test_build_count_sql_skip_existing_has_left_join():
    sql = _build_count_sql(skip_existing=True)
    assert "LEFT JOIN embeddings_e5_v2" in sql
    assert "IS NULL" in sql


def test_build_count_sql_skip_existing_filters_body():
    sql = _build_count_sql(skip_existing=True)
    assert "section_type" in sql
    assert "body" in sql


def test_build_count_sql_all_counts_chunks_v2():
    sql = _build_count_sql(skip_existing=False)
    assert "chunks_v2" in sql
    assert "section_type" in sql
    assert "body" in sql


def test_build_iter_sql_with_limit():
    sql = _build_iter_sql(skip_existing=True, limit=500)
    assert "LIMIT 500" in sql


def test_build_iter_sql_no_limit():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "LIMIT" not in sql


def test_build_iter_sql_selects_embed_text():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "embed_text" in sql


def test_build_iter_sql_targets_embeddings_e5_v2():
    sql = _build_iter_sql(skip_existing=True, limit=None)
    assert "embeddings_e5_v2" in sql
    assert "embeddings_e5" not in sql.replace("embeddings_e5_v2", "")
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_embeddings_v2.py -v
```

Expected: `ImportError` (파일 없음)

- [ ] **Step 3: embeddings_v2.py 작성**

`service/etl/loader/embeddings_v2.py` 전체 내용:

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from pgvector.psycopg2 import register_vector

from service.rag.models.config import EmbeddingModelType
from service.rag.models.encoder import EmbeddingEncoder

ROOT = Path(__file__).resolve().parents[3]

UPSERT_SQL = """
INSERT INTO embeddings_e5_v2 (chunk_id, embedding)
VALUES (%s, %s)
ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
"""


def _connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )
    register_vector(conn)
    return conn


def _parse_db_row(row: tuple) -> dict:
    return {"id": row[0], "chunk_id": row[1], "embed_text": row[2]}


def _build_count_sql(skip_existing: bool) -> str:
    if skip_existing:
        return """
        SELECT COUNT(*)
        FROM chunks_v2 c
        LEFT JOIN embeddings_e5_v2 e ON e.chunk_id = c.chunk_id
        WHERE c.section_type = 'body'
          AND e.chunk_id IS NULL
        """
    return "SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body'"


def _build_iter_sql(skip_existing: bool, limit: int | None) -> str:
    if skip_existing:
        sql = """
        SELECT c.id, c.chunk_id, c.embed_text
        FROM chunks_v2 c
        LEFT JOIN embeddings_e5_v2 e ON e.chunk_id = c.chunk_id
        WHERE c.section_type = 'body'
          AND e.chunk_id IS NULL
        ORDER BY c.id
        """
    else:
        sql = """
        SELECT id, chunk_id, embed_text
        FROM chunks_v2
        WHERE section_type = 'body'
        ORDER BY id
        """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql


def run(
    limit: int | None = None,
    batch_size: int = 100,
    force: bool = False,
) -> dict:
    """embed_text 임베딩 실행. 반환값: {"embedded": int, "skipped": int}"""
    conn = _connect()
    encoder = EmbeddingEncoder(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    skip_existing = not force
    with conn.cursor() as cur:
        cur.execute(_build_count_sql(skip_existing=True))
        total_pending = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body'")
        total_all = int(cur.fetchone()[0])
    skipped = total_all - total_pending

    if total_pending == 0:
        print("[embed_v2] 미임베딩 청크 없음 — 모두 최신 상태입니다.")
        conn.close()
        return {"embedded": 0, "skipped": skipped}

    mode = "전체 재임베딩" if force else "신규 청크만"
    print(f"[embed_v2] {mode} | 대상: {total_pending}개")

    iter_sql = _build_iter_sql(skip_existing=skip_existing, limit=limit)
    batch: list[dict] = []
    processed = 0
    batch_num = 0

    with conn.cursor() as cur:
        cur.execute(iter_sql)
        while True:
            rows = cur.fetchmany(200)
            if not rows:
                break
            for row in rows:
                batch.append(_parse_db_row(row))
                if len(batch) >= batch_size:
                    _flush(batch, encoder, conn, batch_num := batch_num + 1)
                    processed += len(batch)
                    batch = []

    if batch:
        _flush(batch, encoder, conn, batch_num + 1)
        processed += len(batch)

    print(f"[embed_v2] done total_embedded={processed}")
    conn.close()
    return {"embedded": processed, "skipped": skipped}


def _flush(
    batch: list[dict],
    encoder: EmbeddingEncoder,
    conn: psycopg2.extensions.connection,
    batch_num: int,
) -> None:
    chunk_ids = [c["chunk_id"] for c in batch]
    texts = [c["embed_text"] for c in batch]
    vectors = encoder.encode_documents(texts, batch_size=len(texts))
    rows = list(zip(chunk_ids, vectors))
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, rows)
    conn.commit()
    print(f"[embed_v2] batch {batch_num}: upsert={len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(limit=args.limit, batch_size=args.batch_size, force=args.force)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_embeddings_v2.py -v
```

Expected: `10 passed`

- [ ] **Step 5: 커밋**

```bash
git add service/etl/loader/embeddings_v2.py tests/test_embeddings_v2.py
git commit -m "feat: embeddings_v2 — embed_text 기반 임베딩 + 단위 테스트"
```

---

### Task 4: run_pipeline_v2.py 확장 — loader + embeddings 포함

**Files:**
- Modify: `service/etl/run_pipeline_v2.py` (현재 4단계 → 6단계)

**Interfaces:**
- Consumes: Tasks 1-3 모듈의 함수
- Produces: 전체 파이프라인 (ETL → 적재 → 임베딩) 순차 실행

> 이 Task는 DB 연결 없이 실행 불가능한 run() 함수를 추가하는 것이 목적. 단위 테스트는 기존 35개 v2 테스트 회귀 확인으로 대체.

- [ ] **Step 1: run_pipeline_v2.py 수정**

현재 내용을 아래로 교체:

```python
from __future__ import annotations

from service.etl.extractor import extractor_v2
from service.etl.transform import normalizer_v2, parser_v2, chunker_v2
from service.etl.loader import jsonl_to_postgres_v2, embeddings_v2


def run_etl() -> None:
    """ETL 4단계: JSONL 산출물 생성."""
    print("=== ETL v2 파이프라인 시작 ===\n")
    print("[1/4] extractor_v2 — page별 raw_text 추출")
    extractor_v2.main()
    print("\n[2/4] normalizer_v2 — 잡음 제거 + section_type")
    normalizer_v2.main()
    print("\n[3/4] parser_v2 — speaker turn 구조화")
    parser_v2.main()
    print("\n[4/4] chunker_v2 — 짧은 turn 병합 + embed_text")
    chunker_v2.main()
    print("\n=== ETL v2 완료 ===")


def run_load() -> None:
    """적재 2단계: chunks_v2 → embeddings_e5_v2."""
    print("\n=== 적재 v2 시작 ===\n")
    print("[5/6] jsonl_to_postgres_v2 — chunks_v2 테이블 upsert")
    jsonl_to_postgres_v2.main()
    print("\n[6/6] embeddings_v2 — embed_text 임베딩")
    embeddings_v2.main()
    print("\n=== 적재 v2 완료 ===")


def run() -> None:
    """전체 파이프라인: ETL + 적재 + 임베딩."""
    run_etl()
    run_load()


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: v2 단위 테스트 회귀 확인**

```powershell
pytest tests/test_extractor_v2.py tests/test_normalizer_v2.py tests/test_parser_v2.py tests/test_chunker_v2.py tests/test_jsonl_to_postgres_v2.py tests/test_embeddings_v2.py -v
```

Expected: `56 passed` (5+12+9+10+11+10 = 57, 실제 수는 테스트 파일 내용 확인)

- [ ] **Step 3: v1 회귀 테스트**

```powershell
pytest tests/test_normalizer.py tests/test_chunker.py tests/test_retriever.py -v
```

Expected: `41 passed`

- [ ] **Step 4: 커밋**

```bash
git add service/etl/run_pipeline_v2.py
git commit -m "feat: run_pipeline_v2 — ETL + 적재 + 임베딩 6단계 통합 실행"
```
