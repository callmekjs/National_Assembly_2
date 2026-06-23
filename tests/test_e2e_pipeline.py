"""
RAG 파이프라인 E2E 통합 테스트 (실제 DB 필요)

실행:
  pytest tests/test_e2e_pipeline.py -v --pg-port 5433
"""
import sys
from pathlib import Path

import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestE2EPipeline:

    def test_db_connection(self, db_conn):
        """DB 연결 및 chunks 테이블 접근 가능 확인."""
        assert db_conn.closed == 0
        with db_conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1

    def test_chunks_exist_and_schema(self, sample_chunks):
        """chunks 테이블에 데이터가 있고 스키마 계약을 만족하는지 확인."""
        assert len(sample_chunks) >= 1, "chunks 테이블에 데이터가 없습니다"
        chunk_id, text, metadata = sample_chunks[0]
        assert chunk_id, "chunk_id가 비어있습니다"
        assert text, "text가 비어있습니다"
        assert isinstance(metadata, dict), f"metadata가 dict가 아닙니다: {type(metadata)}"

    def test_embeddings_exist_and_dimension(self, db_conn, sample_chunks):
        """embeddings_e5 테이블에 레코드가 있고 벡터 차원이 384인지 확인."""
        import json
        chunk_ids = [row[0] for row in sample_chunks]
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, embedding FROM embeddings_e5 WHERE chunk_id = ANY(%s) LIMIT 1",
                (chunk_ids,),
            )
            row = cur.fetchone()
        assert row is not None, "embeddings_e5에 해당 chunk_id 레코드가 없습니다"
        raw = row[1]
        # pgvector adapter 미등록 시 벡터가 문자열('[0.1, 0.2, ...]')로 반환됨
        if isinstance(raw, str):
            embedding = json.loads(raw)
        else:
            embedding = list(raw)
        assert len(embedding) == 384, f"벡터 차원 불일치: {len(embedding)} (기대값 384)"

    def test_search_returns_results(self, pg_port):
        """Retriever.search가 실제 DB에서 결과를 반환하는지 확인."""
        from service.rag.retrieval.retriever import Retriever
        from service.rag.models.config import EmbeddingModelType

        retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
        results = retriever.search("한미동맹 논의", top_k=3)

        assert len(results) >= 1, "검색 결과가 없습니다"
        first = results[0]
        assert "content" in first, "결과에 'content' 키가 없습니다"
        assert "chunk_id" in first, "결과에 'chunk_id' 키가 없습니다"
        assert "hybrid_score" in first, "결과에 'hybrid_score' 키가 없습니다"
        assert isinstance(first["hybrid_score"], float), "hybrid_score가 float이 아닙니다"

    def test_generate_with_citations(self, pg_port):
        """Generator.generate_with_citations가 비어있지 않은 답변을 반환하는지 확인."""
        from service.rag.retrieval.retriever import Retriever
        from service.rag.models.config import EmbeddingModelType
        from service.rag.generation.generator import Generator

        retriever = Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)
        retrieved = retriever.search("한미동맹에 대한 최근 논의", top_k=3)

        generator = Generator()
        answer = generator.generate_with_citations("한미동맹에 대한 최근 논의는?", retrieved)

        assert answer, "답변이 비어있습니다"
        assert len(answer) > 10, f"답변이 너무 짧습니다: '{answer}'"
        assert re.search(r'\[\d+\]', answer) or "근거:" in answer, \
            f"답변에 출처 표기가 없습니다: '{answer[:100]}'"
