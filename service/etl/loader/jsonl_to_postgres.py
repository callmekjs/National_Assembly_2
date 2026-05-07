from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )


def load_jsonl_files(jsonl_dir: Path, batch_size: int = 1000) -> bool:
    target = Path(jsonl_dir)
    files = sorted(target.glob("*.jsonl"))
    if not files:
        return False

    conn = _connect()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for file_path in files:
                rows = []
                with file_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        rows.append(
                            (
                                row.get("chunk_id", ""),
                                row.get("source_id", ""),
                                row.get("text", ""),
                                Json(row.get("metadata", {})),
                            )
                        )
                        if len(rows) >= batch_size:
                            _insert_rows(cur, rows)
                            rows.clear()
                if rows:
                    _insert_rows(cur, rows)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def _insert_rows(cur, rows: list[tuple]) -> None:
    cur.executemany(
        """
        INSERT INTO chunks (chunk_id, source_id, text, metadata)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (chunk_id) DO UPDATE
        SET
            source_id = EXCLUDED.source_id,
            text = EXCLUDED.text,
            metadata = EXCLUDED.metadata
        """,
        rows,
    )
