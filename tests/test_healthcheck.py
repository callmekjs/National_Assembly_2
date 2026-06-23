"""
scripts/healthcheck.py CLI 테스트 (실제 DB 필요: PG_PORT=5433)

실행:
  pytest tests/test_healthcheck.py -v --pg-port 5433
"""
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


class TestHealthcheck:

    def test_success_with_real_db(self, pg_port):
        """실제 DB에서 4단계 모두 통과."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", str(pg_port)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"exit 1:\n{result.stdout}\n{result.stderr}"
        assert "모든 헬스 체크 통과" in result.stdout
        assert "[✅] Postgres 연결" in result.stdout
        assert "[✅] chunks 테이블" in result.stdout
        assert "[✅] embeddings_e5 테이블" in result.stdout
        assert "[✅] 벡터 차원: 384" in result.stdout

    def test_failure_on_bad_port(self):
        """존재하지 않는 포트 → exit 1 + 연결 실패 메시지."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", "9999"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 1
        assert "[❌] Postgres 연결 실패" in result.stdout
        assert "헬스 체크 실패" in result.stdout

    def test_skip_shown_on_connection_failure(self):
        """연결 실패 시 이후 단계는 ⏭️ 없이 종료 (연결 단계에서 즉시 종료)."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", "9999"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 1
        # 연결 실패 시 chunks/embeddings 체크는 아예 출력되지 않음
        assert "chunks 테이블" not in result.stdout
