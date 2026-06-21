from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_step(name: str, cmd: list[str], env: dict[str, str]) -> None:
    print(f"\n[smoke][{name}] START")
    print(f"[smoke][{name}] cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    if result.returncode != 0:
        print(f"[smoke][{name}] FAIL (exit={result.returncode})")
        raise RuntimeError(f"[{name}] command failed: {' '.join(cmd)}")
    print(f"[smoke][{name}] OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl->ETL->Load->Search 스모크 테스트")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--repeat-load", action="store_true", help="load doc+vector twice (idempotency smoke)")
    parser.add_argument("--query", default="대북정책 핵심 쟁점은?")
    args = parser.parse_args()

    env = os.environ.copy()
    env["PG_PORT"] = str(args.pg_port)
    env.setdefault("PYTHONIOENCODING", "utf-8")

    py = [sys.executable]
    if not args.skip_crawl:
        run_step("crawl", py + ["crawling.py"], env)
    run_step("extract", py + ["-m", "service.etl.extractor.extractor"], env)
    run_step("transform", py + ["-m", "service.etl.transform.pipeline"], env)
    run_step("db_create", py + ["-m", "service.etl.loader.loader_cli", "db", "create"], env)

    def load_once(tag: str) -> None:
        run_step(f"load_doc_{tag}", py + ["-m", "service.etl.loader.loader_cli", "load", "doc", "--jsonl-dir", "data/transform/final"], env)
        run_step(f"load_vector_{tag}", py + ["-m", "service.etl.loader.loader_cli", "load", "vector"], env)

    load_once("1")
    if args.repeat_load:
        print("\n[smoke] repeat-load: second pass (doc + vector)")
        load_once("2")

    run_step(
        "search_smoke",
        py
        + [
            "-c",
            (
                "from service.rag.retrieval.retriever import Retriever;"
                "from service.rag.models.config import EmbeddingModelType;"
                f"q={args.query!r};"
                "r=Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL);"
                "res=r.search(q, top_k=3);"
                "print('Search hits:', len(res));"
                "[print('[{}] sim={:.3f} source={} text={}'.format(i+1,x.get('similarity',0),x.get('source_id',''),(x.get('content','') or '')[:120])) for i,x in enumerate(res)]"
            ),
        ],
        env,
    )
    print("\n[smoke_pipeline] all steps completed")


if __name__ == "__main__":
    main()
