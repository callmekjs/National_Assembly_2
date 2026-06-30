from __future__ import annotations

import contextlib
from typing import Any, Generator

import psycopg2
from psycopg2 import pool as pg_pool
from pgvector.psycopg2 import register_vector

from config.vector_database import get_vector_db_config
from service.rag.interfaces.vector_store import SearchResult
from service.speaker_aliases import (
    extract_speaker_marker,
    has_hanja,
    normalize_speaker_name,
    speaker_alias_variants,
)

_POOL: pg_pool.ThreadedConnectionPool | None = None
_POOL_CFG: dict = {}


def _build_pool(cfg: dict) -> pg_pool.ThreadedConnectionPool:
    conn_cfg = {**cfg, "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}
    return pg_pool.ThreadedConnectionPool(minconn=1, maxconn=5, **conn_cfg)


class PgVectorStore:
    def __init__(self, db_config: dict[str, Any] | None = None):
        global _POOL, _POOL_CFG
        cfg = db_config or get_vector_db_config().get_db_config()
        if _POOL is None or _POOL_CFG != cfg:
            if _POOL is not None:
                try:
                    _POOL.closeall()
                except Exception:
                    pass
            _POOL_CFG = cfg
            _POOL = _build_pool(cfg)
        self._pool = _POOL
        self._conn_cfg = {**cfg, "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}

    @contextlib.contextmanager
    def _conn(self):
        conn = self._pool.getconn()
        try:
            if conn.closed:
                conn = psycopg2.connect(**self._conn_cfg)
            else:
                try:
                    with conn.cursor() as _c:
                        _c.execute("SELECT 1")
                    conn.rollback()
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = psycopg2.connect(**self._conn_cfg)
            register_vector(conn)
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                self._pool.putconn(conn)
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._pool is not None

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
                where, speaker_params = _build_speaker_like_filter(
                    speaker,
                    speaker_expr="COALESCE(c.metadata->>'speaker', '')",
                    text_expr="COALESCE(c.text, '')",
                )
                where_parts.append(where)
                params.extend(speaker_params)
            if bool(filters.get("require_speaker")):
                where_parts.append(
                    "(COALESCE(c.metadata->>'speaker', '') <> '' "
                    "OR COALESCE(c.metadata->>'speaker_original', '') <> '' "
                    "OR COALESCE(c.text, '') ~ '^[[:space:]]*[○◯]')"
                )

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        sql += """
        ORDER BY e.embedding <=> %s::vector, c.chunk_id ASC
        LIMIT %s
        """
        params.extend([query_embedding, top_k])

        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            _build_search_result(
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
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO embeddings_e5 (chunk_id, embedding)
                VALUES (%s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
                """,
                rows,
            )
        return len(rows)

    def count_chunks_to_process(self, _model_type=None, skip_existing: bool = True) -> int:
        with self._conn() as conn, conn.cursor() as cur:
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

        with self._conn() as conn, conn.cursor() as cur:
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
               1 - (e.embedding <=> %s::vector) AS sim, c.metadata,
               c.speaker, c.speaker_role, c.page_no
        FROM embeddings_e5_v2 e
        JOIN chunks_v2 c ON c.chunk_id = e.chunk_id
        WHERE {where}
        ORDER BY e.embedding <=> %s::vector, c.chunk_id ASC
        LIMIT %s
        """
        params = [query_embedding] + filter_params + [query_embedding, top_k]
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            _build_search_result(
                chunk_id=row[0],
                source_id=row[1] or "",
                content=row[2] or "",
                similarity=float(row[3] or 0.0),
                metadata=_merge_page_meta(row[4], row[7]),
                speaker=row[5] or "",
                speaker_role=row[6] or "",
            )
            for row in rows
        ]

    def search_keyword_v2(
        self,
        query_text: str,
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """chunks_v2.clean_text PostgreSQL FTS 검색.

        plainto_tsquery (AND) 대신 토큰 OR 쿼리를 사용해 한국어 recall을 높인다.
        2자 이상 한글/영문/숫자 토큰을 추출해 'tok1 | tok2 | tok3' 형식의 to_tsquery로 변환.
        """
        import re as _re
        tokens = _re.findall(r"[가-힣\u3400-\u9fff\uf900-\ufaffa-zA-Z0-9]{2,}", query_text)
        if not tokens:
            return []
        ts_expr = " | ".join(tokens)
        where, filter_params = _build_v2_filter_where(filters)
        sql = f"""
        SELECT c.chunk_id, c.source_id, c.clean_text,
               ts_rank(to_tsvector('simple', c.clean_text),
                       to_tsquery('simple', %s)) AS rank,
               c.metadata, c.speaker, c.speaker_role, c.page_no
        FROM chunks_v2 c
        WHERE {where}
          AND to_tsvector('simple', c.clean_text) @@ to_tsquery('simple', %s)
        ORDER BY rank DESC, c.chunk_id ASC
        LIMIT %s
        """
        params = [ts_expr] + filter_params + [ts_expr, top_k]
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            _build_search_result(
                chunk_id=row[0],
                source_id=row[1] or "",
                content=row[2] or "",
                similarity=float(row[3] or 0.0),
                metadata=_merge_page_meta(row[4], row[7]),
                speaker=row[5] or "",
                speaker_role=row[6] or "",
            )
            for row in rows
        ]


    def fetch_chunks_by_ids(
        self,
        chunk_ids: list[str],
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """chunk_id 목록으로 chunks_v2 데이터를 조회 (sparse search 결과 enrichment용)."""
        if not chunk_ids:
            return []
        placeholders = ",".join(["%s"] * len(chunk_ids))
        where, filter_params = _build_v2_filter_where(filters)
        sql = f"""
        SELECT c.chunk_id, c.source_id, c.clean_text,
               0.0 AS sim, c.metadata, c.speaker, c.speaker_role, c.page_no
        FROM chunks_v2 c
        WHERE {where}
          AND c.chunk_id IN ({placeholders})
        """
        params = filter_params + list(chunk_ids)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [
            _build_search_result(
                chunk_id=row[0],
                source_id=row[1] or "",
                content=row[2] or "",
                similarity=float(row[3] or 0.0),
                metadata=_merge_page_meta(row[4], row[7]),
                speaker=row[5] or "",
                speaker_role=row[6] or "",
            )
            for row in rows
        ]


def _merge_page_meta(metadata: dict | None, page_no) -> dict:
    meta = dict(metadata or {})
    if page_no is not None:
        meta["page_no"] = int(page_no)
    return meta


def _to_iso_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD. 이미 ISO 형식이면 그대로 반환."""
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _build_speaker_like_filter(
    speaker: str,
    *,
    speaker_expr: str,
    text_expr: str,
) -> tuple[str, list]:
    variants = speaker_alias_variants(speaker)
    clauses: list[str] = []
    params: list = []
    for variant in variants:
        pattern = f"%{variant}%"
        for expr in (
            speaker_expr,
            "COALESCE(c.metadata->>'speaker_original', '')",
        ):
            clauses.append(f"{expr} LIKE %s")
            params.append(pattern)
        for marker in ("◯", "○"):
            clauses.append(f"{text_expr} LIKE %s")
            params.append(f"%{marker}{variant}%")
            clauses.append(f"{text_expr} LIKE %s")
            params.append(f"%{marker} {variant}%")
    return "(" + " OR ".join(clauses) + ")", params


def _filter_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw = value
    elif isinstance(value, str) and value.strip():
        raw = [value]
    else:
        raw = []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        key = "".join(text.split())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _build_office_scope_filter(
    *,
    role_terms: list[str],
    agencies: list[str],
    text_expr: str,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    for term in _filter_values(role_terms):
        pattern = f"%{term}%"
        for expr in (
            "COALESCE(c.speaker_role, '')",
            "COALESCE(c.metadata->>'speaker_role', '')",
            text_expr,
        ):
            clauses.append(f"{expr} LIKE %s")
            params.append(pattern)
    for agency in _filter_values(agencies):
        pattern = f"%{agency}%"
        clauses.append("COALESCE(c.metadata->>'agency', '') = %s")
        params.append(agency)
        clauses.append(f"{text_expr} LIKE %s")
        params.append(pattern)
    if not clauses:
        return "", []
    return "(" + " OR ".join(clauses) + ")", params


def _build_search_result(
    *,
    chunk_id: str,
    source_id: str,
    content: str,
    similarity: float,
    metadata: dict | None,
    speaker: str = "",
    speaker_role: str = "",
    embedding: list[float] | None = None,
) -> SearchResult:
    meta, normalized_speaker, normalized_role = _normalize_result_speaker(
        content=content,
        metadata=metadata,
        speaker=speaker,
        speaker_role=speaker_role,
    )
    return SearchResult(
        chunk_id=chunk_id,
        source_id=source_id,
        content=content,
        similarity=similarity,
        metadata=meta,
        speaker=normalized_speaker,
        speaker_role=normalized_role,
        embedding=embedding,
    )


def _normalize_result_speaker(
    *,
    content: str,
    metadata: dict | None,
    speaker: str = "",
    speaker_role: str = "",
) -> tuple[dict, str, str]:
    meta = dict(metadata or {})
    stored_speaker = str(speaker or meta.get("speaker") or "").strip()
    stored_role = str(speaker_role or meta.get("speaker_role") or "").strip()
    detected_speaker, detected_role, detected_original = extract_speaker_marker(content)

    normalized_stored = normalize_speaker_name(stored_speaker)
    final_speaker = detected_speaker or normalized_stored
    final_role = detected_role or stored_role

    if final_speaker:
        meta["speaker"] = final_speaker
    if final_role:
        meta["speaker_role"] = final_role
    if detected_original:
        meta["speaker_original"] = detected_original
    elif stored_speaker and stored_speaker != normalized_stored and has_hanja(stored_speaker):
        meta.setdefault("speaker_original", stored_speaker)

    return meta, final_speaker, final_role


def _build_v2_filter_where(filters: dict | None) -> tuple[str, list]:
    """chunks_v2 검색용 WHERE 절 생성. 첫 항목은 항상 section_type='body'."""
    parts: list[str] = ["c.section_type = 'body'"]
    params: list = []
    if filters:
        committee = str(filters.get("committee") or "").strip()
        date_from = _to_iso_date(str(filters.get("date_from") or "").strip())
        date_to = _to_iso_date(str(filters.get("date_to") or "").strip())
        speaker = str(filters.get("speaker") or "").strip()
        question_type = str(filters.get("question_type") or filters.get("question_type_filter") or "").strip()
        utterance_type = str(filters.get("utterance_type") or "").strip()
        party = str(filters.get("party") or "").strip()
        position_type = str(filters.get("position_type") or "").strip()
        agency = str(filters.get("agency") or "").strip()
        speaker_role = str(filters.get("speaker_role") or "").strip()
        office_terms = _filter_values(filters.get("office_terms"))
        office_agencies = _filter_values(filters.get("office_agencies"))
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
            where, speaker_params = _build_speaker_like_filter(
                speaker,
                speaker_expr="COALESCE(c.speaker, '')",
                text_expr="COALESCE(c.clean_text, '')",
            )
            parts.append(where)
            params.extend(speaker_params)
        role_terms = _filter_values([speaker_role] + office_terms)
        if role_terms or office_agencies:
            where, office_params = _build_office_scope_filter(
                role_terms=role_terms,
                agencies=office_agencies,
                text_expr="COALESCE(c.clean_text, '')",
            )
            if where:
                parts.append(where)
                params.extend(office_params)
        if question_type:
            parts.append("(c.metadata->'question_type_hints') ? %s")
            params.append(question_type)
        if utterance_type:
            parts.append("COALESCE(c.metadata->>'utterance_type', '') = %s")
            params.append(utterance_type)
        if party:
            parts.append("COALESCE(c.metadata->>'party', '') = %s")
            params.append(party)
        if position_type:
            parts.append("COALESCE(c.metadata->>'position_type', '') = %s")
            params.append(position_type)
        if agency:
            parts.append("COALESCE(c.metadata->>'agency', '') = %s")
            params.append(agency)
        if bool(filters.get("require_speaker")):
            parts.append(
                "(COALESCE(c.speaker, '') <> '' "
                "OR COALESCE(c.metadata->>'speaker_original', '') <> '' "
                "OR COALESCE(c.clean_text, '') ~ '^[[:space:]]*[○◯]')"
            )
    # chunk_type: 기본값 'utterance' (qa_pair가 일반 검색에 혼입되지 않도록)
    chunk_type = str(filters.get("chunk_type") or "utterance").strip() if filters else "utterance"
    parts.append("COALESCE(c.metadata->>'chunk_type', 'utterance') = %s")
    params.append(chunk_type)
    return " AND ".join(parts), params
