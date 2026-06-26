from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")
logger = logging.getLogger(__name__)

_LOAD_SQL = """
SELECT chunk_id, sparse_weights
FROM embeddings_e5_v2
WHERE sparse_weights IS NOT NULL
"""


class SparseIndex:
    """BGE-M3 lexical_weights 기반 in-memory inverted index."""

    def __init__(self) -> None:
        # token -> list of (chunk_id, weight)
        self._inverted: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self._built = False

    def build_from_db(self) -> int:
        conn = psycopg2.connect(
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", "5432")),
            database=os.getenv("PG_DB", "skn_project"),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", "post1234"),
        )
        try:
            self._inverted.clear()
            count = 0
            with conn.cursor() as cur:
                cur.execute(_LOAD_SQL)
                while True:
                    rows = cur.fetchmany(500)
                    if not rows:
                        break
                    for chunk_id, weights_json in rows:
                        if not weights_json:
                            continue
                        weights = weights_json if isinstance(weights_json, dict) else json.loads(weights_json)
                        for token, weight in weights.items():
                            self._inverted[token].append((chunk_id, float(weight)))
                        count += 1
            self._built = True
            logger.info("[SparseIndex] built: %d chunks, %d tokens", count, len(self._inverted))
            return count
        finally:
            conn.close()

    def search(self, query_weights: dict[str, float], top_k: int) -> list[dict]:
        if not self._built:
            return []
        scores: dict[str, float] = {}
        for token, q_weight in query_weights.items():
            for chunk_id, d_weight in self._inverted.get(token, []):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + float(q_weight) * d_weight
        top = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
        return [{"chunk_id": cid, "sparse_score": score} for cid, score in top]

    @property
    def is_built(self) -> bool:
        return self._built


_instance: SparseIndex | None = None


def get_sparse_index() -> SparseIndex:
    global _instance
    if _instance is None:
        _instance = SparseIndex()
        _instance.build_from_db()
    return _instance
