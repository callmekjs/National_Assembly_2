from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SearchResult:
    chunk_id: str
    source_id: str
    content: str
    similarity: float
    metadata: dict[str, Any]


class VectorStore(Protocol):
    def search_similar(self, query_embedding: list[float], top_k: int = 5) -> list[SearchResult]:
        ...
