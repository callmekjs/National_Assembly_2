"""
service.rag.retrieval.retriever 단위 테스트 (DB 없이 mock 사용)

실행:
  pytest tests/test_retriever.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Retriever 초기화 없이 내부 메서드만 테스트 ───────────────────────

class TestRetrieverInternalMethods:
    """DB/모델 없이 Retriever 내부 로직만 테스트."""

    @pytest.fixture
    def retriever(self):
        with patch("service.rag.retrieval.retriever.EmbeddingEncoder"), \
             patch("service.rag.retrieval.retriever.PgVectorStore"):
            from service.rag.retrieval.retriever import Retriever
            from service.rag.models.config import EmbeddingModelType
            return Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    def test_lexical_overlap_exact_match(self, retriever):
        # "조태열"은 완전 일치, "발언"은 content에서 형태소 변형(발언했습니다) → 1/2 이상
        score = retriever._lexical_overlap_score("조태열 발언", "조태열 외교부장관이 발언했습니다")
        assert score >= 0.5

    def test_lexical_overlap_no_match(self, retriever):
        score = retriever._lexical_overlap_score("조태열", "전혀 다른 내용입니다")
        assert score == 0.0

    def test_lexical_overlap_empty_query(self, retriever):
        score = retriever._lexical_overlap_score("", "내용이 있습니다")
        assert score == 0.0

    def test_domain_keyword_boost_hanmi(self, retriever):
        boost = retriever._domain_keyword_boost("한미동맹 현황", "한미동맹 강화를 위한 논의")
        assert boost > 0

    def test_domain_keyword_boost_no_match(self, retriever):
        boost = retriever._domain_keyword_boost("날씨 이야기", "오늘 날씨가 맑습니다")
        assert boost == 0.0

    def test_expand_query_hanmi(self, retriever):
        expanded = retriever._expand_query("한미동맹 논의")
        assert "한미훈련" in expanded

    def test_expand_query_no_expansion(self, retriever):
        q = "북한의 최근 동향"
        expanded = retriever._expand_query(q)
        assert q in expanded

    def test_expand_query_empty(self, retriever):
        result = retriever._expand_query("")
        assert result == ""

    def test_dedupe_by_chunk_id(self, retriever):
        docs = [
            {"chunk_id": "a", "hybrid_score": 0.9},
            {"chunk_id": "a", "hybrid_score": 0.7},  # 중복
            {"chunk_id": "b", "hybrid_score": 0.8},
        ]
        deduped = retriever._dedupe_by_chunk_id(docs)
        ids = [d["chunk_id"] for d in deduped]
        assert ids.count("a") == 1
        assert len(deduped) == 2

    def test_balance_speakers_round_robin(self, retriever):
        docs = [
            {"chunk_id": "a1", "metadata": {"speaker": "조태열"}, "hybrid_score": 0.9},
            {"chunk_id": "a2", "metadata": {"speaker": "조태열"}, "hybrid_score": 0.85},
            {"chunk_id": "b1", "metadata": {"speaker": "정동영"}, "hybrid_score": 0.8},
            {"chunk_id": "b2", "metadata": {"speaker": "정동영"}, "hybrid_score": 0.75},
        ]
        balanced = retriever._balance_speakers(docs, top_k=3)
        speakers = [d["metadata"]["speaker"] for d in balanced]
        assert "조태열" in speakers
        assert "정동영" in speakers
        assert len(balanced) == 3


# ── _lexical_overlap_score 경계 케이스 ──────────────────────────────

class TestLexicalOverlapEdgeCases:
    @pytest.fixture
    def retriever(self):
        with patch("service.rag.retrieval.retriever.EmbeddingEncoder"), \
             patch("service.rag.retrieval.retriever.PgVectorStore"):
            from service.rag.retrieval.retriever import Retriever
            from service.rag.models.config import EmbeddingModelType
            return Retriever(EmbeddingModelType.MULTILINGUAL_E5_SMALL)

    def test_score_between_0_and_1(self, retriever):
        score = retriever._lexical_overlap_score("외교 정책 논의", "외교 정책에 대한 논의가 있었습니다")
        assert 0.0 <= score <= 1.0

    def test_single_char_token_ignored(self, retriever):
        # 1자 토큰은 필터링됨
        score = retriever._lexical_overlap_score("에 를 이 가", "에 를 이 가 있습니다")
        assert score == 0.0  # 2자 미만 토큰 전부 무시
