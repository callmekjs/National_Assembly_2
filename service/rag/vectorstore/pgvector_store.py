from __future__ import annotations

from typing import Any, Generator

import psycopg2
from pgvector.psycopg2 import register_vector

from config.vector_database import get_vector_db_config
from service.rag.interfaces.vector_store import SearchResult


class PgVectorStore:
    def __init__(self, db_config: dict[str, Any] | None = None):
        cfg = db_config or get_vector_db_config().get_db_config()
        self.conn = psycopg2.connect(**cfg)
        register_vector(self.conn)

    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.closed == 0

    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        return_embeddings: bool = False,
    ) -> list[SearchResult]:
        emb_col = ", e.embedding" if return_embeddings else ""
        sql = f"""
        SELECT c.chunk_id, c.source_id, c.text, 1 - (e.embedding <=> %s::vector) AS sim, c.metadata{emb_col}
        FROM embeddings_e5 e
        JOIN chunks c ON c.chunk_id = e.chunk_id
        """
        params: list[Any] = [query_embedding]

        where_parts: list[str] = []
        if filters:
            committee = str(filters.get("committee") or "").strip()
            date_from = str(filters.get("date_from") or "").strip()
            date_to = str(filters.get("date_to") or "").strip()
            if committee:
                where_parts.append("COALESCE(c.metadata->>'committee', '') = %s")
                params.append(committee)
            if date_from:
                where_parts.append("COALESCE(c.metadata->>'meeting_date', '') >= %s")
                params.append(date_from)
            if date_to:
                where_parts.append("COALESCE(c.metadata->>'meeting_date', '') <= %s")
                params.append(date_to)
            speaker = str(filters.get("speaker") or "").strip()
            if speaker:
                where_parts.append("COALESCE(c.metadata->>'speaker', '') LIKE %s")
                params.append(f"%{speaker}%")

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        sql += """
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
        """
        params.extend([query_embedding, top_k])

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
                embedding=list(row[5]) if return_embeddings and len(row) > 5 and row[5] is not None else None,
            )
            for row in rows
        ]

    def insert_embeddings(self, _model_type, chunk_ids: list[str], embeddings: list[list[float]]) -> int:
        rows = list(zip(chunk_ids, embeddings))
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO embeddings_e5 (chunk_id, embedding)
                VALUES (%s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
                """,
                rows,
            )
        self.conn.commit()
        return len(rows)

    def count_chunks_to_process(self, _model_type=None, skip_existing: bool = True) -> int:
        with self.conn.cursor() as cur:
            if skip_existing:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM chunks c
                    LEFT JOIN embeddings_e5 e ON e.chunk_id = c.chunk_id
                    WHERE e.chunk_id IS NULL
                    """
                )
            else:
                cur.execute("SELECT COUNT(*) FROM chunks")
            return int(cur.fetchone()[0])

    def iter_chunks_to_process(
        self, _model_type=None, skip_existing: bool = True, limit: int | None = None, fetch_size: int = 200
    ) -> Generator[dict[str, Any], None, None]:
        sql = "SELECT id, chunk_id, text, metadata FROM chunks"
        if skip_existing:
            sql = """
            SELECT c.id, c.chunk_id, c.text, c.metadata
            FROM chunks c
            LEFT JOIN embeddings_e5 e ON e.chunk_id = c.chunk_id
            WHERE e.chunk_id IS NULL
            """
        sql += " ORDER BY id"
        if limit:
            sql += f" LIMIT {int(limit)}"

        with self.conn.cursor() as cur:
            cur.execute(sql)
            while True:
                batch = cur.fetchmany(fetch_size)
                if not batch:
                    break
                for row in batch:
                    yield {"id": row[0], "chunk_id": row[1], "natural_text": row[2], "metadata": row[3] or {}}

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
