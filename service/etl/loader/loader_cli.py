from __future__ import annotations

import argparse
from pathlib import Path

from service.etl.loader.embeddings import run as run_embeddings
from service.etl.loader.jsonl_to_postgres import load_jsonl_files
from service.etl.loader.system_manager import create_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Load CLI")
    sub = parser.add_subparsers(dest="command")

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command")
    db_sub.add_parser("create")

    load = sub.add_parser("load")
    load_sub = load.add_subparsers(dest="load_command")

    doc = load_sub.add_parser("doc")
    doc.add_argument("--jsonl-dir", type=Path, default=Path("data/transform/final"))
    doc.add_argument("--batch-size", type=int, default=1000)

    vec = load_sub.add_parser("vector")
    vec.add_argument("--batch-size", type=int, default=100)
    vec.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.command == "db" and args.db_command == "create":
        print("ok" if create_schema() else "fail")
        return
    if args.command == "load" and args.load_command == "doc":
        print("ok" if load_jsonl_files(args.jsonl_dir, args.batch_size) else "fail")
        return
    if args.command == "load" and args.load_command == "vector":
        run_embeddings(limit=args.limit, batch_size=args.batch_size)
        print("ok")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
