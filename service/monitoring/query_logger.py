"""
쿼리 로그 저장 + 검색 실패 감지 + 단계별 latency 기록.

사용:
    from service.monitoring.query_logger import log_query, setup_table, get_recent_failures

테이블 초기화 (앱 기동 시 1회):
    setup_table()
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras


def _conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5433")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )


def setup_table() -> None:
    """query_logs 테이블이 없으면 생성."""
    ddl = """
    CREATE TABLE IF NOT EXISTS query_logs (
        id            SERIAL PRIMARY KEY,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        question      TEXT        NOT NULL,
        answer_preview TEXT,
        grounding_level VARCHAR(10),
        doc_count     INT         DEFAULT 0,
        is_recall_zero BOOLEAN    DEFAULT FALSE,
        committee     VARCHAR(100),
        latency_total_ms  FLOAT,
        latency_retrieve_ms FLOAT,
        latency_generate_ms FLOAT
    );
    CREATE INDEX IF NOT EXISTS idx_query_logs_created ON query_logs (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_query_logs_recall  ON query_logs (is_recall_zero) WHERE is_recall_zero = TRUE;
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)
        conn.commit()


def log_query(
    *,
    question: str,
    answer: str = "",
    grounding_level: str = "",
    doc_count: int = 0,
    committee: Optional[str] = None,
    latency_total_ms: Optional[float] = None,
    latency_retrieve_ms: Optional[float] = None,
    latency_generate_ms: Optional[float] = None,
) -> int:
    """쿼리 1건을 query_logs 에 저장하고 삽입된 id 반환."""
    is_recall_zero = doc_count == 0
    answer_preview = answer[:300] if answer else ""

    sql = """
    INSERT INTO query_logs
        (question, answer_preview, grounding_level, doc_count,
         is_recall_zero, committee,
         latency_total_ms, latency_retrieve_ms, latency_generate_ms)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (
                question, answer_preview, grounding_level, doc_count,
                is_recall_zero, committee,
                latency_total_ms, latency_retrieve_ms, latency_generate_ms,
            ))
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else -1
    except Exception as e:
        # 로그 실패가 메인 응답을 막으면 안 됨
        print(f"[query_logger] log_query failed: {e}")
        return -1


def get_recent_logs(limit: int = 50) -> list[dict]:
    """최근 쿼리 로그 반환."""
    sql = """
    SELECT id, created_at, question, grounding_level, doc_count,
           is_recall_zero, committee, latency_total_ms
    FROM query_logs
    ORDER BY created_at DESC
    LIMIT %s
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[query_logger] get_recent_logs failed: {e}")
        return []


def get_recent_failures(limit: int = 20) -> list[dict]:
    """recall=0 (검색 실패) 쿼리만 반환."""
    sql = """
    SELECT id, created_at, question, committee, latency_total_ms
    FROM query_logs
    WHERE is_recall_zero = TRUE
    ORDER BY created_at DESC
    LIMIT %s
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[query_logger] get_recent_failures failed: {e}")
        return []


def get_stats() -> dict:
    """전체 통계 요약 반환."""
    sql = """
    SELECT
        COUNT(*)                                         AS total,
        COUNT(*) FILTER (WHERE is_recall_zero)          AS recall_zero,
        ROUND(AVG(latency_total_ms)::numeric, 1)        AS avg_latency_ms,
        ROUND(AVG(latency_retrieve_ms)::numeric, 1)     AS avg_retrieve_ms,
        ROUND(AVG(latency_generate_ms)::numeric, 1)     AS avg_generate_ms,
        COUNT(*) FILTER (WHERE grounding_level = 'FULL')    AS grounding_full,
        COUNT(*) FILTER (WHERE grounding_level = 'PARTIAL') AS grounding_partial,
        COUNT(*) FILTER (WHERE grounding_level = 'NONE')    AS grounding_none
    FROM query_logs
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                row = cur.fetchone()
                return dict(row) if row else {}
    except Exception as e:
        print(f"[query_logger] get_stats failed: {e}")
        return {}
