from __future__ import annotations

import argparse
import os

from service.rag.generation.generator import Generator
from service.rag.models.config import EmbeddingModelType
from service.rag.retrieval.retriever import Retriever


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 + 근거 인용 답변 데모")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--committee", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    args = parser.parse_args()

    os.environ["PG_PORT"] = str(args.pg_port)
    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    generator = Generator()

    results = retriever.search(
        query=args.query,
        top_k=args.top_k,
        committee=args.committee or None,
        date_from=args.date_from or None,
        date_to=args.date_to or None,
        include_metadata=True,
    )
    print(f"Search hits: {len(results)}")
    answer = generator.generate_with_citations(args.query, results)
    print("\n=== ANSWER ===")
    print(answer)


if __name__ == "__main__":
    main()
