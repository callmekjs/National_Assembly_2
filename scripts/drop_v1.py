#!/usr/bin/env python3
"""Drop v1 RAG tables (chunks, embeddings_e5) from Postgres."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Drop v1 tables: chunks, embeddings_e5")
    p.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    p.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5433")))
    p.add_argument("--pg-db", default=os.getenv("PG_DB", "skn_project"))
    p.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    p.add_argument("--pg-password", default=os.getenv("PG_PASSWORD", "post1234"))
    p.add_argument(
        "--terminate-sessions",
        action="store_true",
        default=True,
        help="Terminate other sessions on this DB before DROP (default: on)",
    )
    p.add_argument(
        "--no-terminate-sessions",
        action="store_false",
        dest="terminate_sessions",
        help="Do not terminate other sessions",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    import psycopg2

    target = f"{args.pg_host}:{args.pg_port}/{args.pg_db}"
    print(f"[drop_v1] connecting {target} ...")
    try:
        conn = psycopg2.connect(
            host=args.pg_host,
            port=args.pg_port,
            database=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
            connect_timeout=5,
        )
    except Exception as exc:
        print(f"[drop_v1] connection failed: {exc}", file=sys.stderr)
        return 1

    conn.autocommit = True
    cur = conn.cursor()

    if args.terminate_sessions:
        cur.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (args.pg_db,),
        )
        n = sum(1 for row in cur.fetchall() if row[0])
        if n:
            print(f"[drop_v1] terminated other sessions: {n}")
            time.sleep(1)

    print("[drop_v1] dropping embeddings_e5 ...")
    cur.execute("DROP TABLE IF EXISTS embeddings_e5 CASCADE")
    print("[drop_v1] dropping chunks ...")
    cur.execute("DROP TABLE IF EXISTS chunks CASCADE")
    print("v1 테이블 삭제 완료")

    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    print("남은 테이블:", [r[0] for r in cur.fetchall()])
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
