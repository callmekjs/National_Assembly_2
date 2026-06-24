# 데이터 파이프라인 Retrieval v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `embeddings_e5_v2` + `chunks_v2` 테이블을 사용하는 진짜 Hybrid 검색 경로를 추가한다. vector top-50 + PostgreSQL FTS top-50 → RRF 병합. 기존 v1 검색 경로는 100% 유지.

**Architecture:** 3개 기존 파일에 메서드/함수를 additive하게 추가. 새 파일 없음. `meta["use_v2_retrieval"] = True`로 v1/v2 토글. v2 검색 결과 dict는 v1과 동일한 필드 구조를 유지해 하위 LLM 노드가 투명하게 사용 가능.

**Tech Stack:** psycopg2, pgvector, PostgreSQL FTS (plainto_tsquery/tsvector), pytest

## Global Constraints

- v1 경로(`search()`, `search_similar()`, `fusion_search()` 등) 수정 금지
- `search_v2()` 반환 dict 필드: `content, chunk_id, source_id, date, similarity, hybrid_score, metadata` (v1 `search()` 출력 구조 일치)
- `content` 필드 = `chunks_v2.clean_text` (v1은 `chunks.text`)
- speaker 필터: v2에서는 `chunks_v2.speaker` 컬럼 직접 사용 (v1은 `metadata->>'speaker'`)
- RRF 공식: `score(d) += 1 / (k + rank)`, k=60, 두 리스트 rank는 1-based
- `_rrf_merge` 입력은 `list[dict]`; chunk_id로 중복 제거 (첫 등장 dict 보존)
- FTS 쿼리: `plainto_tsquery('simple', query)` (한국어 토크나이저 없이 simple 사용)
- `ROOT = Path(__file__).resolve().parents[X]` 이 플랜에서는 Path 사용 없음
- `_build_v2_filter_where` 첫 항목은 항상 `"c.section_type = 'body'"`

---

## File Map

| 파일 | 상태 | 변경 내용 |
|------|------|----------|
| `service/rag/vectorstore/pgvector_store.py` | 수정 | `_build_v2_filter_where()`, `search_similar_v2()`, `search_keyword_v2()` 추가 |
| `service/rag/retrieval/retriever.py` | 수정 | `_rrf_merge()`, `search_v2()` 추가 |
| `graph/nodes/retrieve_pg.py` | 수정 | `use_v2_retrieval` 메타 토글 추가 |
| `tests/test_pgvector_store_v2.py` | 신규 | `_build_v2_filter_where` 단위 테스트 7개 |
| `tests/test_retriever_v2.py` | 신규 | `_rrf_merge` 단위 테스트 8개 |

---

### Task 1: pgvector_store.py — v2 검색 메서드 추가

**Files:**
- Modify: `service/rag/vectorstore/pgvector_store.py`
- Create: `tests/test_pgvector_store_v2.py`

**Interfaces:**
- Produces (module-level pure function):
  - `_build_v2_filter_where(filters: dict | None) -> tuple[str, list]` — WHERE 절 + params
- Produces (new methods on PgVectorStore):
  - `search_similar_v2(query_embedding, top_k, filters) -> list[SearchResult]` — chunks_v2 + embeddings_e5_v2
  - `search_keyword_v2(query_text, top_k, filters) -> list[SearchResult]` — FTS on chunks_v2.clean_text

- [ ] **Step 1: 테스트 작성**

`tests/test_pgvector_store_v2.py` 전체 내용:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.vectorstore.pgvector_store import _build_v2_filter_where


def test_empty_filters_body_only():
    where, params = _build_v2_filter_where(None)
    assert "c.section_type = 'body'" in where
    assert params == []


def test_empty_dict_body_only():
    where, params = _build_v2_filter_where({})
    assert "c.section_type = 'body'" in where
    assert params == []


def test_committee_filter():
    where, params = _build_v2_filter_where({"committee": "외교통일위원회"})
    assert "committee" in where
    assert "외교통일위원회" in params


def test_date_from_filter():
    where, params = _build_v2_filter_where({"date_from": "2024-01-01"})
    assert ">=" in where
    assert "2024-01-01" in params


def test_date_to_filter():
    where, params = _build_v2_filter_where({"date_to": "2024-12-31"})
    assert "<=" in where
    assert "2024-12-31" in params


def test_speaker_filter_uses_column_not_metadata():
    where, params = _build_v2_filter_where({"speaker": "김철수"})
    assert "c.speaker" in where
    assert "metadata" not in where
    assert "%김철수%" in params


def test_multiple_filters_combined():
    where, params = _build_v2_filter_where({
        "committee": "외교통일위원회",
        "date_from": "2024-01-01",
        "speaker": "김철수",
    })
    assert where.count(" AND ") >= 3
    assert len(params) == 3
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
cd C:\National_Assembly_2
pytest tests/test_pgvector_store_v2.py -v
```

Expected: `ImportError: cannot import name '_build_v2_filter_where'`

- [ ] **Step 3: pgvector_store.py에 추가**

파일 끝에 아래 코드를 추가 (기존 코드 수정 없음):

```python


def _build_v2_filter_where(filters: dict | None) -> tuple[str, list]:
    """chunks_v2 검색용 WHERE 절 생성. 첫 항목은 항상 section_type='body'."""
    parts: list[str] = ["c.section_type = 'body'"]
    params: list = []
    if not filters:
        return " AND ".join(parts), params
    committee = str(filters.get("committee") or "").strip()
    date_from = str(filters.get("date_from") or "").strip()
    date_to = str(filters.get("date_to") or "").strip()
    speaker = str(filters.get("speaker") or "").strip()
    if committee:
        parts.append("COALESCE(c.metadata->>'committee', '') = %s")
        params.append(committee)
    if date_from:
        parts.append("COALESCE(c.metadata->>'meeting_date', '') >= %s")
        params.append(date_from)
    if date_to:
        parts.append("COALESCE(c.metadata->>'meeting_date', '') <= %s")
        params.append(date_to)
    if speaker:
        parts.append("COALESCE(c.speaker, '') LIKE %s")
        params.append(f"%{speaker}%")
    return " AND ".join(parts), params
```

그리고 `PgVectorStore` 클래스 끝에 두 메서드를 추가:

```python
    def search_similar_v2(
        self,
        query_embedding: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """embeddings_e5_v2 + chunks_v2 기반 벡터 검색."""
        where, filter_params = _build_v2_filter_where(filters)
        sql = f"""
        SELECT c.chunk_id, c.source_id, c.clean_text,
               1 - (e.embedding <=> %s::vector) AS sim, c.metadata
        FROM embeddings_e5_v2 e
        JOIN chunks_v2 c ON c.chunk_id = e.chunk_id
        WHERE {where}
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
        """
        params = [query_embedding] + filter_params + [query_embedding, top_k]
        with self.conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            SearchResult(
                chunk_id=row[0],
                source_id=row[1] or "",
                content=row[2] or "",
                similarity=float(row[3] or 0.0),
                metadata=row[4] or {},
            )
            for row in rows
        ]

    def search_keyword_v2(
        self,
        query_text: str,
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """chunks_v2.clean_text PostgreSQL FTS 검색."""
        where, filter_params = _build_v2_filter_where(filters)
        sql = f"""
        SELECT c.chunk_id, c.source_id, c.clean_text,
               ts_rank(to_tsvector('simple', c.clean_text),
                       plainto_tsquery('simple', %s)) AS rank,
               c.metadata
        FROM chunks_v2 c
        WHERE {where}
          AND to_tsvector('simple', c.clean_text) @@ plainto_tsquery('simple', %s)
        ORDER BY rank DESC
        LIMIT %s
        """
        params = [query_text] + filter_params + [query_text, top_k]
        with self.conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            SearchResult(
                chunk_id=row[0],
                source_id=row[1] or "",
                content=row[2] or "",
                similarity=float(row[3] or 0.0),
                metadata=row[4] or {},
            )
            for row in rows
        ]
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_pgvector_store_v2.py -v
```

Expected: `7 passed`

- [ ] **Step 5: v1 회귀 확인**

```powershell
pytest tests/test_retriever.py -v
```

Expected: `12 passed` (v1 retriever 테스트 회귀 없음)

- [ ] **Step 6: 커밋**

```bash
git add service/rag/vectorstore/pgvector_store.py tests/test_pgvector_store_v2.py
git commit -m "feat: pgvector_store — search_similar_v2 + search_keyword_v2 + FTS (chunks_v2)"
```

---

### Task 2: retriever.py — _rrf_merge + search_v2 추가

**Files:**
- Modify: `service/rag/retrieval/retriever.py`
- Create: `tests/test_retriever_v2.py`

**Interfaces:**
- Consumes (from Task 1): `store.search_similar_v2()`, `store.search_keyword_v2()`
- Produces (module-level pure function):
  - `_rrf_merge(vector_hits: list[dict], fts_hits: list[dict], k: int = 60, top_n: int | None = None) -> list[dict]`
- Produces (new method on Retriever):
  - `search_v2(query, top_k, committee, date_from, date_to, speaker, use_neural_reranker) -> list[dict]`

**`_rrf_merge` 알고리즘:**
- `score[chunk_id] += 1 / (k + rank)` (rank는 1-based, k=60)
- 두 리스트를 순회; chunk_id 중복이면 score 누적, dict는 첫 등장 보존
- 최종 `sorted(items, key=score, reverse=True)[:top_n]`
- 출력 각 dict에 `rrf_score` 필드 추가

- [ ] **Step 1: 테스트 작성**

`tests/test_retriever_v2.py` 전체 내용:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.rag.retrieval.retriever import _rrf_merge


def _hit(chunk_id: str, content: str = "내용") -> dict:
    return {"chunk_id": chunk_id, "content": content, "similarity": 0.9, "source_id": "src"}


def test_empty_both_returns_empty():
    assert _rrf_merge([], []) == []


def test_vector_only():
    result = _rrf_merge([_hit("A"), _hit("B")], [])
    assert [r["chunk_id"] for r in result] == ["A", "B"]


def test_fts_only():
    result = _rrf_merge([], [_hit("C"), _hit("D")])
    assert [r["chunk_id"] for r in result] == ["C", "D"]


def test_overlap_deduplicates():
    vector = [_hit("A"), _hit("B")]
    fts = [_hit("B"), _hit("C")]
    result = _rrf_merge(vector, fts)
    ids = [r["chunk_id"] for r in result]
    assert len(ids) == len(set(ids))


def test_overlap_boosts_score():
    # B가 두 리스트 모두 rank=1 → A(벡터 rank=2)보다 높아야 함
    vector = [_hit("A"), _hit("B")]
    fts = [_hit("B"), _hit("C")]
    result = _rrf_merge(vector, fts)
    ids = [r["chunk_id"] for r in result]
    assert ids[0] == "B"


def test_top_n_limits_output():
    vector = [_hit(f"V{i}") for i in range(10)]
    fts = [_hit(f"F{i}") for i in range(10)]
    result = _rrf_merge(vector, fts, top_n=5)
    assert len(result) == 5


def test_rrf_score_field_present():
    result = _rrf_merge([_hit("A")], [])
    assert "rrf_score" in result[0]


def test_rrf_score_correct_formula():
    # rank=1, k=60 → score = 1/61
    result = _rrf_merge([_hit("A")], [])
    assert abs(result[0]["rrf_score"] - 1 / 61) < 1e-9
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_retriever_v2.py -v
```

Expected: `ImportError: cannot import name '_rrf_merge'`

- [ ] **Step 3: retriever.py에 추가**

파일 최상단 `from __future__ import annotations` 바로 다음에 아래 함수를 모듈 레벨로 추가:

```python
def _rrf_merge(
    vector_hits: list[dict],
    fts_hits: list[dict],
    k: int = 60,
    top_n: int | None = None,
) -> list[dict]:
    """Reciprocal Rank Fusion. score(d) += 1/(k+rank). chunk_id로 중복 제거."""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    for rank, hit in enumerate(vector_hits, start=1):
        cid = hit.get("chunk_id", "")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in items:
            items[cid] = hit
    for rank, hit in enumerate(fts_hits, start=1):
        cid = hit.get("chunk_id", "")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in items:
            items[cid] = hit
    merged = sorted(items.values(), key=lambda x: scores.get(x.get("chunk_id", ""), 0.0), reverse=True)
    if top_n is not None:
        merged = merged[:top_n]
    for hit in merged:
        hit["rrf_score"] = scores.get(hit.get("chunk_id", ""), 0.0)
    return merged
```

그리고 `Retriever` 클래스 끝에 `search_v2()` 메서드를 추가:

```python
    def search_v2(
        self,
        query: str,
        top_k: int = 5,
        committee: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        speaker: str | None = None,
        use_neural_reranker: bool = False,
    ) -> list[dict]:
        """True Hybrid: vector top-50 + FTS top-50 → RRF → top_k."""
        from service.rag.retrieval.date_range import normalize_meeting_date_range
        vector = self.encoder.encode_query(query)
        df, dt = normalize_meeting_date_range(date_from, date_to)
        filters = {
            "committee": committee or "",
            "date_from": df or "",
            "date_to": dt or "",
            "speaker": speaker or "",
        }
        vector_results = self.store.search_similar_v2(vector, top_k=50, filters=filters)
        fts_results = self.store.search_keyword_v2(query, top_k=50, filters=filters)

        def _to_dict(row: "SearchResult") -> dict:
            return {
                "content": row.content,
                "chunk_id": row.chunk_id,
                "source_id": row.source_id,
                "date": row.metadata.get("meeting_date", ""),
                "title": row.metadata.get("section", ""),
                "url": row.metadata.get("url", ""),
                "similarity": row.similarity,
                "hybrid_score": row.similarity,
                "metadata": row.metadata,
            }

        vec_dicts = [_to_dict(r) for r in vector_results]
        fts_dicts = [_to_dict(r) for r in fts_results]
        merged = _rrf_merge(vec_dicts, fts_dicts, k=60, top_n=top_k * 10)

        for hit in merged:
            hit["hybrid_score"] = hit.get("rrf_score", 0.0)

        if use_neural_reranker and merged:
            from service.rag.retrieval.reranker import create_neural_reranker
            merged = create_neural_reranker().rerank(query, merged, top_k=top_k)
        else:
            merged = merged[:top_k]

        return merged
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_retriever_v2.py -v
```

Expected: `8 passed`

- [ ] **Step 5: v1 회귀 확인**

```powershell
pytest tests/test_retriever.py -v
```

Expected: `12 passed`

- [ ] **Step 6: 커밋**

```bash
git add service/rag/retrieval/retriever.py tests/test_retriever_v2.py
git commit -m "feat: retriever — _rrf_merge + search_v2 (vector + FTS → RRF)"
```

---

### Task 3: retrieve_pg.py — use_v2_retrieval 토글 연결

**Files:**
- Modify: `graph/nodes/retrieve_pg.py`

**Interfaces:**
- Consumes: `retriever.search_v2()` (Task 2)
- Toggle: `meta.get("use_v2_retrieval", False)` → True면 v2 경로, False면 기존 v1 경로

> Task 3는 side-effecting 노드 수정이므로 단위 테스트 없음. v1 전체 회귀 테스트로 검증.

- [ ] **Step 1: retrieve_pg.py 수정**

`run()` 함수 내에서 `comparison_subjects` 처리 전에 `use_v2_retrieval` 플래그를 읽는 코드를 추가:

기존 (라인 143 근처):
```python
    eval_recall = bool(meta.get("eval_recall", False))
```

아래 코드를 기존 라인 바로 다음에 추가:
```python
    use_v2_retrieval = bool(meta.get("use_v2_retrieval", False))
```

그리고 기존 비교 쿼리 분기 (`if len(comparison_subjects) == 2:`) 전체 블록을 다음으로 교체:

```python
    # v2 검색 경로 (use_v2_retrieval=True)
    if use_v2_retrieval:
        results = retriever.search_v2(
            query=query,
            top_k=top_k,
            committee=committee,
            date_from=date_from,
            date_to=date_to,
            use_neural_reranker=bool(meta.get("use_neural_reranker", False)),
        )
    # v1 검색 경로 (기존 로직 완전 유지)
    elif len(comparison_subjects) == 2:
        per_k = max(top_k * 2, 15)
        seen_ids: set[str] = set()
        results = []
        for i, subj_kw in enumerate(comparison_subjects):
            speaker_name = subj_kw[0]
            other_name = comparison_subjects[1 - i][0]
            topic_query = query.replace(other_name, "")
            topic_query = re.sub(r'\s+', ' ', topic_query).strip()
            subj_query = " ".join(subj_kw) + " " + topic_query
            subj_results = retriever.search(query=subj_query, top_k=per_k, speaker=speaker_name, **_search_kwargs)
            for r in subj_results:
                cid = r.get("chunk_id") or r.get("source_id") or ""
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    results.append(r)
        print(f"[Retrieve] 비교쿼리 분리 검색: {len(results)}개 병합")
    else:
        results = retriever.search(query=query, top_k=top_k, **_search_kwargs)
```

- [ ] **Step 2: v1 전체 회귀 테스트**

```powershell
pytest tests/test_normalizer.py tests/test_chunker.py tests/test_retriever.py tests/test_pgvector_store_v2.py tests/test_retriever_v2.py -v
```

Expected: `41 + 7 + 8 = 56 passed`

- [ ] **Step 3: 커밋**

```bash
git add graph/nodes/retrieve_pg.py
git commit -m "feat: retrieve_pg — use_v2_retrieval 토글 (meta 플래그로 v1/v2 선택)"
```
