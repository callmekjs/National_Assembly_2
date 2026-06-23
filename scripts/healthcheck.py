#!/usr/bin/env python3
"""
헬스 체크 CLI — Postgres + pgvector 데이터 존재 여부 확인

실행:
  python scripts/healthcheck.py
  python scripts/healthcheck.py --pg-port 5433
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

# Windows: force stdout/stderr to UTF-8 so emoji characters don't crash on cp949
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postgres + pgvector 헬스 체크")
    parser.add_argument("--pg-host", default=os.environ.get("PG_HOST", "localhost"))
    parser.add_argument("--pg-port", type=int, default=int(os.environ.get("PG_PORT", "5432")))
    parser.add_argument("--pg-db", default=os.environ.get("PG_DB", "skn_project"))
    parser.add_argument("--pg-user", default=os.environ.get("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.environ.get("PG_PASSWORD", "post1234"))
    return parser.parse_args()


def _ok(msg: str) -> None:
    print(f"[✅] {msg}")


def _fail(msg: str) -> None:
    print(f"[❌] {msg}")


def _skip(msg: str) -> None:
    print(f"[⏭️] {msg} (이전 단계 실패로 건너뜀)")


def main() -> int:
    args = _get_args()
    conn_str = f"{args.pg_host}:{args.pg_port}/{args.pg_db}"

    # Step 1: Postgres 연결
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=args.pg_host,
            port=args.pg_port,
            database=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
        )
        _ok(f"Postgres 연결 ({conn_str})")
    except Exception as exc:
        _fail(f"Postgres 연결 실패: {exc}")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        return 1

    # Step 2: chunks 테이블
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            count = int(cur.fetchone()[0])
        if count == 0:
            _fail("chunks 테이블: 0건 (데이터 없음)")
            _skip("embeddings_e5 테이블")
            _skip("벡터 차원")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"chunks 테이블: {count:,}건")
    except Exception as exc:
        _fail(f"chunks 테이블 조회 실패: {exc}")
        _skip("embeddings_e5 테이블")
        _skip("벡터 차원")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    # Step 3: embeddings_e5 테이블
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM embeddings_e5")
            count = int(cur.fetchone()[0])
        if count == 0:
            _fail("embeddings_e5 테이블: 0건 (임베딩 없음)")
            _skip("벡터 차원")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"embeddings_e5 테이블: {count:,}건")
    except Exception as exc:
        _fail(f"embeddings_e5 테이블 조회 실패: {exc}")
        _skip("벡터 차원")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    # Step 4: 벡터 차원
    try:
        try:
            from pgvector.psycopg2 import register_vector
            register_vector(conn)
        except Exception:
            pass
        with conn.cursor() as cur:
            cur.execute("SELECT embedding FROM embeddings_e5 LIMIT 1")
            row = cur.fetchone()
        if row is None:
            _fail("벡터 차원 확인 실패: 레코드 없음")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        emb = row[0]
        if isinstance(emb, str):
            emb = json.loads(emb)
        dim = len(list(emb))
        if dim != 384:
            _fail(f"벡터 차원 불일치: {dim} (기대값 384)")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"벡터 차원: {dim}")
    except Exception as exc:
        _fail(f"벡터 차원 확인 실패: {exc}")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    conn.close()
    print("\n모든 헬스 체크 통과 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
