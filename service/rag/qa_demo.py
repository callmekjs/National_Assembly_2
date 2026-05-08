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
    parser.add_argument("--alpha", type=float, default=0.8, help="vector vs lexical blend (1.0=vector only)")
    parser.add_argument("--return-k", type=int, default=5, help="final returned chunk count")
    parser.add_argument("--committee", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--use-reranker", action="store_true")
    parser.add_argument("--balance-speakers", action="store_true")
    parser.add_argument("--pg-port", default=os.getenv("PG_PORT", "5432"))
    args = parser.parse_args()

    os.environ["PG_PORT"] = str(args.pg_port)
    retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
    generator = Generator()

    results = retriever.search(
        query=args.query,
        top_k=args.top_k,
        alpha=args.alpha,
        committee=args.committee or None,
        date_from=args.date_from or None,
        date_to=args.date_to or None,
        include_metadata=True,
        use_reranker=args.use_reranker,
        balance_speakers=args.balance_speakers,
    )
    results = results[: max(1, int(args.return_k))]
    print(f"Search hits: {len(results)}")
    answer = generator.generate_with_citations(args.query, results)
    print("\n=== ANSWER ===")
    print(answer)


if __name__ == "__main__":
    main()
