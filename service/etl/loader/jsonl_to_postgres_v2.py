from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")
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


DEFAULT_QA_JSONL = ROOT / "data" / "v2" / "transform" / "qa_pairs" / "qa_pairs_v2.jsonl"


def load_qa_pairs(jsonl_path: Path | None = None, batch_size: int = 1000) -> bool:
    """QA 쌍 JSONL을 chunks_v2에 upsert. 기존 load_chunks_v2 재사용."""
    path = Path(jsonl_path) if jsonl_path else DEFAULT_QA_JSONL
    if not path.exists():
        print(f"[loader_v2] QA 쌍 파일 없음 (스킵): {path}")
        return True  # 파일 없음은 에러가 아님 (첫 실행 등)
    return load_chunks_v2(jsonl_path=path, batch_size=batch_size)


def main() -> None:
    load_chunks_v2()
    load_qa_pairs()


if __name__ == "__main__":
    main()
