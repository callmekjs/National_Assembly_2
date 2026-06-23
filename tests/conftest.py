import os
import sys
from pathlib import Path

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_addoption(parser):
    parser.addoption("--pg-port", action="store", default="5432", help="PostgreSQL port for E2E tests")


@pytest.fixture(scope="session")
def pg_port(request):
    port = int(request.config.getoption("--pg-port"))
    os.environ["PG_PORT"] = str(port)
    from config.vector_database import DatabaseConfig, update_db_config
    update_db_config(DatabaseConfig.from_env())
    return port


@pytest.fixture(scope="session")
def db_conn(pg_port):
    try:
        conn = psycopg2.connect(
            host=os.environ.get("PG_HOST", "localhost"),
            port=pg_port,
            database=os.environ.get("PG_DB", "skn_project"),
            user=os.environ.get("PG_USER", "postgres"),
            password=os.environ.get("PG_PASSWORD", "post1234"),
        )
    except Exception as exc:
        pytest.skip(f"DB 연결 실패 (PG_PORT={pg_port}): {exc}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def sample_chunks(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT chunk_id, text, metadata FROM chunks LIMIT 5")
        rows = cur.fetchall()
    return rows
