"""
chunks_v2 테이블의 utterance_type을 현재 infer_utterance_type() 로직으로 재계산해 업데이트.

실행:
  python scripts/retag_utterance_type.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import psycopg2
from psycopg2.extras import execute_values
from service.rag.query.question_types import infer_utterance_type, infer_utterance_type_with_confidence, infer_chunk_question_type_hints

FETCH_SQL = """
SELECT chunk_id, clean_text, speaker, speaker_role,
       metadata->>'position_type'    AS position_type,
       metadata->>'utterance_type'   AS old_utype
FROM chunks_v2
ORDER BY id
"""

UPDATE_SQL = """
UPDATE chunks_v2
SET metadata = metadata
    || jsonb_build_object('utterance_type', data.new_utype::text)
    || jsonb_build_object('question_type_hints', data.new_hints::jsonb)
    || jsonb_build_object('utterance_type_confidence', data.new_conf::float)
FROM (VALUES %s) AS data(chunk_id, new_utype, new_hints, new_conf)
WHERE chunks_v2.chunk_id = data.chunk_id
"""

BATCH = 2000


def main() -> None:
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )
    conn.autocommit = False

    print("[retag] 청크 로딩 중...")
    with conn.cursor() as cur:
        cur.execute(FETCH_SQL)
        rows = cur.fetchall()
    print(f"[retag] {len(rows):,}개 청크 로드 완료")

    changed = 0
    total = len(rows)
    updates: list[tuple] = []

    import json
    for i, (chunk_id, text, speaker, speaker_role, position_type, old_utype) in enumerate(rows):
        new_utype, new_conf = infer_utterance_type_with_confidence(text or "", speaker_role or "", position_type or "")
        new_hints = infer_chunk_question_type_hints(
            text or "", speaker or "", speaker_role or "",
            {"position_type": position_type or "", "utterance_type": new_utype}
        )
        updates.append((chunk_id, new_utype, json.dumps(new_hints, ensure_ascii=False), round(new_conf, 2)))
        if new_utype != (old_utype or ""):
            changed += 1

        if len(updates) >= BATCH:
            _flush(conn, updates)
            done = i + 1
            pct = done / total * 100
            print(f"[retag] {done:,}/{total:,} ({pct:.1f}%) - 변경 누적: {changed:,}")
            updates.clear()

    if updates:
        _flush(conn, updates)

    conn.close()

    print(f"\n[retag] 완료 — 총 {total:,}개 중 {changed:,}개 utterance_type 변경됨")

    # 최종 분포 출력
    conn2 = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )
    with conn2.cursor() as cur:
        cur.execute("""
            SELECT metadata->>'utterance_type', COUNT(*)
            FROM chunks_v2
            GROUP BY metadata->>'utterance_type'
            ORDER BY 2 DESC
        """)
        print("\n[retag] 최종 utterance_type 분포:")
        for utype, cnt in cur.fetchall():
            print(f"  {utype:<12} {cnt:>7,}")
    conn2.close()


def _flush(conn: psycopg2.extensions.connection, updates: list[tuple]) -> None:
    with conn.cursor() as cur:
        execute_values(cur, UPDATE_SQL, updates, template="(%s, %s, %s::jsonb, %s)")
    conn.commit()


if __name__ == "__main__":
    main()
