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
    ) -> list[SearchResult]:
        sql = """
        SELECT c.chunk_id, c.source_id, c.text, 1 - (e.embedding <=> %s::vector) AS sim, c.metadata
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
