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
DEFAULT_QA_JSONL = ROOT / "data" / "v2" / "transform" / "qa_pairs" / "qa_pairs_v2.jsonl"

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


def load_qa_pairs(jsonl_path: Path | None = None, batch_size: int = 1000) -> bool:
    """QA 쌍 JSONL을 chunks_v2에 upsert. 기존 load_chunks_v2 재사용."""
    path = Path(jsonl_path) if jsonl_path else DEFAULT_QA_JSONL
    if not path.exists():
        print(f"[loader_v2] QA 쌍 파일 없음 (스킵): {path}")
        return True  # 파일 없음은 에러가 아님 (첫 실행 등)
    return load_chunks_v2(jsonl_path=path, batch_size=batch_size)


def _iter_jsonl_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def sync_chunks_v2(
    jsonl_paths: list[Path] | None = None,
    batch_size: int = 1000,
    prune_stale: bool = True,
) -> bool:
    """현재 JSONL 파일들을 기준으로 chunks_v2를 동기화한다.

    load_chunks_v2는 upsert만 수행하므로 재생성 후 사라진 chunk_id가 DB에 남을 수 있다.
    이 함수는 현재 파일에 있는 chunk_id를 temp table에 모은 뒤 stale chunk/embedding을 삭제한다.
    """
    paths = jsonl_paths or [DEFAULT_JSONL, DEFAULT_QA_JSONL]
    paths = [Path(p) for p in paths if Path(p).exists()]
    if not paths:
        print("[loader_v2] 동기화할 JSONL 파일이 없습니다.")
        return False

    conn = _connect()
    conn.autocommit = False
    total = 0
    deleted_embeddings = 0
    deleted_chunks = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TEMP TABLE current_chunks_v2_ids "
                "(chunk_id text PRIMARY KEY) ON COMMIT DROP"
            )
            rows: list[tuple] = []
            ids: list[tuple[str]] = []
            for path in paths:
                for row in _iter_jsonl_rows(path):
                    chunk_id = str(row.get("chunk_id") or "").strip()
                    if not chunk_id:
                        continue
                    rows.append(_row_to_tuple(row))
                    ids.append((chunk_id,))
                    if len(rows) >= batch_size:
                        cur.executemany(INSERT_SQL, rows)
                        cur.executemany(
                            "INSERT INTO current_chunks_v2_ids (chunk_id) VALUES (%s) "
                            "ON CONFLICT DO NOTHING",
                            ids,
                        )
                        total += len(rows)
                        rows.clear()
                        ids.clear()
            if rows:
                cur.executemany(INSERT_SQL, rows)
                cur.executemany(
                    "INSERT INTO current_chunks_v2_ids (chunk_id) VALUES (%s) "
                    "ON CONFLICT DO NOTHING",
                    ids,
                )
                total += len(rows)

            if prune_stale:
                cur.execute(
                    """
                    DELETE FROM embeddings_e5_v2 e
                    WHERE NOT EXISTS (
                        SELECT 1 FROM current_chunks_v2_ids ids
                        WHERE ids.chunk_id = e.chunk_id
                    )
                    """
                )
                deleted_embeddings = cur.rowcount
                cur.execute(
                    """
                    DELETE FROM chunks_v2 c
                    WHERE NOT EXISTS (
                        SELECT 1 FROM current_chunks_v2_ids ids
                        WHERE ids.chunk_id = c.chunk_id
                    )
                    """
                )
                deleted_chunks = cur.rowcount
        conn.commit()
        print(
            "[loader_v2] sync_rows={total} stale_chunks_deleted={chunks} "
            "stale_embeddings_deleted={embeddings} → chunks_v2".format(
                total=total,
                chunks=deleted_chunks,
                embeddings=deleted_embeddings,
            )
        )
        return True
    except Exception as e:
        conn.rollback()
        print(f"[loader_v2] SYNC ERROR: {e}")
        return False
    finally:
        conn.close()


def main() -> None:
    sync_chunks_v2()


if __name__ == "__main__":
    main()
