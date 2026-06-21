from __future__ import annotations

import subprocess
from pathlib import Path


def create_schema() -> bool:
    schema_file = Path(__file__).parent / "schema_jsonl.sql"
    if not schema_file.exists():
        return False
    try:
        subprocess.run(
            ["docker", "exec", "-i", "SKN18-3rd", "psql", "-U", "postgres", "-d", "skn_project"],
            input=schema_file.read_text(encoding="utf-8"),
            text=True,
            check=True,
            capture_output=True,
        )
        return True
    except Exception:
        return False
