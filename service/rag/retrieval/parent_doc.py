"""
Parent Document Retrieval
작은 청크(child)로 정밀 검색 → 실제 LLM에는 부모 청크(더 넓은 문맥) 전달.
현재 구조: ◯ 발언자 단위 청크를 child로, 같은 source_id의 연속 청크를 parent로 묶는다.
"""
from __future__ import annotations

from service.rag.vectorstore.pgvector_store import PgVectorStore

_store: PgVectorStore | None = None


def _get_store() -> PgVectorStore:
    global _store
    if _store is None:
        _store = PgVectorStore()
    return _store


def fetch_parent_chunks(
    child_docs: list[dict],
    window: int = 1,
) -> list[dict]:
    """
    child 청크 목록을 받아 각각의 앞뒤 window개 청크까지 포함한 '부모' 컨텍스트를 반환.
    chunk_id 형식: {source_id}_{idx}  (chunker.py 참고)
    """
    store = _get_store()
    enriched: list[dict] = []
    seen_chunk_ids: set[str] = set()

    for doc in child_docs:
        chunk_id: str = str(doc.get("chunk_id") or "")
        source_id: str = str(doc.get("source_id") or doc.get("metadata", {}).get("source_id", ""))

        # chunk_id에서 인덱스 파싱 → {source_id}_{idx}
        idx = _parse_idx(chunk_id, source_id)

        if idx is None:
            # 인덱스 파싱 실패 → 원본 그대로
            if chunk_id not in seen_chunk_ids:
                enriched.append(doc)
                seen_chunk_ids.add(chunk_id)
            continue

        # 앞뒤 window개 chunk_id 수집
        sibling_ids = [
            f"{source_id}_{i}"
            for i in range(max(0, idx - window), idx + window + 1)
        ]

        # DB에서 형제 청크 텍스트 조회
        sibling_texts = _fetch_chunk_texts(store, sibling_ids)

        # 텍스트 합치기 (순서 유지)
        combined = "\n".join(
            sibling_texts[cid]
            for cid in sibling_ids
            if cid in sibling_texts
        ).strip()

        parent_doc = dict(doc)
        if combined and combined != doc.get("content", ""):
            parent_doc["content"] = combined
            parent_doc["_parent_expanded"] = True
            parent_doc["_child_chunk_id"] = chunk_id

        key = chunk_id
        if key not in seen_chunk_ids:
            enriched.append(parent_doc)
            seen_chunk_ids.add(key)

    return enriched


def _parse_idx(chunk_id: str, source_id: str) -> int | None:
    """chunk_id = '{source_id}_{idx}' 에서 idx 추출."""
    if not chunk_id or not source_id:
        return None
    prefix = f"{source_id}_"
    if chunk_id.startswith(prefix):
        tail = chunk_id[len(prefix):]
        if tail.isdigit():
            return int(tail)
    return None


def _fetch_chunk_texts(store: PgVectorStore, chunk_ids: list[str]) -> dict[str, str]:
    """chunk_id 목록으로 DB에서 content 조회. {chunk_id: content} 반환."""
    if not chunk_ids:
        return {}
    try:
        with store.conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, text FROM chunks WHERE chunk_id = ANY(%s)",
                (chunk_ids,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        print(f"[parent_doc] DB 조회 실패: {e}")
        return {}
