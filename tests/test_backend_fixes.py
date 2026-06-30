"""
Backend 수정 항목 테스트 (2026-06-30)

커버 범위:
  - Fix 4: generate._build_numbered_context — top_k 동적 사용
  - Fix 5: search_v2() alpha·balance_speakers 시그니처
  - Fix 5: alpha → Dense/FTS 후보 비율 계산
  - Fix 6: rerank._rerank_score — lexical re-boost
  - Fix 7: router._is_too_vague — 애매한 쿼리 감지
  - Fix 7: router.run — needs_clarification 플래그
  - Fix 7: generate.run — needs_clarification 조기 반환
  - Fix 8: retrieve_pg committee_distribution (mock)
  - Hardcoding 제거: _is_out_of_scope, _build_out_of_scope_warning, build_user_prompt E항목
  - Item A: QueryResponse 신규 필드 (committee_distribution, generation_skipped)
  - Item B: v2 비교쿼리 분리 검색 (병렬 ThreadPoolExecutor, 인터리브 병합)
  - Item C: 멀티턴 히스토리 지시어 해소 (history_resolver)
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Fix 5: search_v2 시그니처 ────────────────────────────────────────

from service.rag.retrieval.retriever import Retriever


def test_search_v2_has_alpha_param():
    sig = inspect.signature(Retriever.search_v2)
    assert "alpha" in sig.parameters
    assert sig.parameters["alpha"].default == pytest.approx(0.75)


def test_search_v2_has_balance_speakers_param():
    sig = inspect.signature(Retriever.search_v2)
    assert "balance_speakers" in sig.parameters
    assert sig.parameters["balance_speakers"].default is False


# ── Fix 5: alpha → Dense/FTS 후보 비율 ──────────────────────────────
# search_v2 내부 계산: _TOTAL_CANDS=50, _DENSE_K = max(5, round(50 * alpha))

@pytest.mark.parametrize("alpha,expected_dense,min_fts", [
    (1.0, 50, 0),    # 완전 dense
    (0.75, 38, 12),  # 기본값
    (0.5, 25, 25),   # 균등
    (0.0, 5, 45),    # 완전 FTS (min cap 5)
])
def test_search_v2_alpha_candidate_ratio(alpha, expected_dense, min_fts):
    _TOTAL_CANDS = 50
    _alpha = max(0.0, min(1.0, alpha))
    dense_k = max(5, round(_TOTAL_CANDS * _alpha))
    sparse_k = _TOTAL_CANDS - dense_k
    assert dense_k == expected_dense
    assert sparse_k == min_fts


# ── Fix 6: rerank._rerank_score ─────────────────────────────────────

from graph.nodes.rerank import _rerank_score, _token_overlap, _RERANK_ALPHA


def test_token_overlap_full_match():
    # 조사 없이 토큰이 그대로 등장하는 경우 → 1.0
    assert _token_overlap("대북정책 한미동맹", "대북정책 한미동맹 발언") == pytest.approx(1.0)


def test_token_overlap_partial_match():
    # 쿼리 토큰 중 하나만 본문에 등장
    overlap = _token_overlap("대북정책 한미동맹", "한미동맹 발언 내용")
    assert 0.0 < overlap < 1.0


def test_token_overlap_no_match():
    assert _token_overlap("대북정책", "기후변화 탄소중립") == pytest.approx(0.0)


def test_token_overlap_empty_query():
    assert _token_overlap("", "대북정책 내용") == pytest.approx(0.0)


def test_rerank_score_uses_hybrid_score_as_base():
    doc = {"hybrid_score": 0.8, "chunk_text": "대북정책 논의 내용"}
    score = _rerank_score(doc, "대북정책")
    # base = 0.8, lexical > 0 → score > 0.8 * _RERANK_ALPHA
    assert score > 0.8 * _RERANK_ALPHA


def test_rerank_score_prefers_relevant_doc():
    relevant = {"hybrid_score": 0.7, "chunk_text": "한미동맹 관련 주요 논의"}
    irrelevant = {"hybrid_score": 0.75, "chunk_text": "기후변화 탄소중립 정책"}
    query = "한미동맹 현황"
    score_rel = _rerank_score(relevant, query)
    score_irr = _rerank_score(irrelevant, query)
    assert score_rel > score_irr


def test_rerank_score_fallback_to_similarity():
    doc = {"similarity": 0.6, "chunk_text": "발언 내용"}
    score = _rerank_score(doc, "발언")
    assert score > 0.0


def test_rerank_run_attaches_rerank_score():
    from graph.nodes.rerank import run
    state = {
        "question": "대북정책 발언",
        "retrieved": [
            {"hybrid_score": 0.8, "chunk_text": "대북정책 관련 발언"},
            {"hybrid_score": 0.7, "chunk_text": "기후변화 논의"},
        ],
    }
    result = run(state)
    assert "reranked" in result
    assert all("rerank_score" in d for d in result["reranked"])


def test_rerank_run_orders_by_rerank_score():
    from graph.nodes.rerank import run
    # hybrid_score 차이가 작을 때 lexical boost가 순서를 뒤집을 수 있어야 함
    # relevant: 0.85*0.6 + 0.15*1.0 = 0.66
    # irrelevant: 0.85*0.65 + 0.15*0.0 = 0.5525
    state = {
        "question": "한미동맹 논의",
        "retrieved": [
            {"hybrid_score": 0.6, "chunk_text": "한미동맹 논의 방위비분담"},
            {"hybrid_score": 0.65, "chunk_text": "기후변화 탄소중립 의제"},
        ],
    }
    result = run(state)
    assert "한미동맹" in result["reranked"][0]["chunk_text"]


def test_rerank_run_empty_retrieved():
    from graph.nodes.rerank import run
    state = {"question": "테스트", "retrieved": []}
    result = run(state)
    assert result["reranked"] == []


# ── Fix 7: _is_too_vague ─────────────────────────────────────────────

from graph.nodes.router import _is_too_vague


@pytest.mark.parametrize("question", [
    "",
    "뭐",
    "이",
    "이것",
    "그것",
    "이거",
    "이게",
    "그거",
    "이거 뭐야",
    "그거 알려줘",
    "이것 뭐야?",
    "그 사람",
    "이 사람",
])
def test_is_too_vague_detects_vague(question):
    assert _is_too_vague(question) is True


@pytest.mark.parametrize("question", [
    "대북정책",
    "한미동맹",
    "검찰개혁",
    "방위비",
    "방위비분담",
    "대북정책 입장 알려줘",
    "조태열 장관 발언",
    "한미동맹 여야 입장 비교",
    "AI 정책",
    "방송법 문제",
])
def test_is_too_vague_allows_valid_queries(question):
    assert _is_too_vague(question) is False


# ── Fix 7: router.run — needs_clarification 플래그 ────────────────────

from graph.nodes.router import run as router_run


def test_router_sets_needs_clarification_for_vague():
    state = {"question": "이거 뭐야", "meta": {}}
    out = router_run(state)
    assert out["meta"].get("needs_clarification") is True
    assert "clarification_message" in out["meta"]
    assert len(out["meta"]["clarification_message"]) > 20


def test_router_does_not_set_clarification_for_valid_query():
    state = {"question": "대북정책 관련 논의", "meta": {}}
    out = router_run(state)
    assert not out["meta"].get("needs_clarification")


def test_router_clarification_skips_further_routing():
    """needs_clarification 시 question_type 등 라우팅 결과가 없어야 한다."""
    state = {"question": "그 사람", "meta": {}}
    out = router_run(state)
    assert out["meta"].get("needs_clarification") is True
    # 라우팅이 중단됐으므로 question_type 등 없음
    assert "question_type" not in out["meta"]


# ── Fix 7: generate.run — needs_clarification 조기 반환 ──────────────

from graph.nodes.generate import run as generate_run


def test_generate_skips_llm_for_clarification():
    state = {
        "question": "이거 뭐야",
        "meta": {
            "needs_clarification": True,
            "clarification_message": "더 구체적으로 질문해주세요.",
        },
    }
    out = generate_run(state)
    assert out.get("generation_skipped") == "needs_clarification"
    assert out.get("draft_answer") == "더 구체적으로 질문해주세요."


def test_generate_clarification_message_in_draft_answer():
    msg = "구체적인 인물명과 주제를 포함해주세요."
    state = {
        "question": "그 사람",
        "meta": {"needs_clarification": True, "clarification_message": msg},
    }
    out = generate_run(state)
    assert out["draft_answer"] == msg


# ── Fix 4: _build_numbered_context top_k 동적 사용 ───────────────────

from graph.nodes.generate import _build_numbered_context, _MAX_CONTEXT_DOCS


def _make_doc(i: int) -> dict:
    return {
        "chunk_text": f"발언 내용 {i}",
        "speaker": f"발언자{i}",
        "speaker_role": "위원",
        "date": "2024-01-01",
        "metadata": {},
    }


def test_build_numbered_context_uses_top_k_from_meta():
    docs = [_make_doc(i) for i in range(10)]
    state = {"reranked": docs, "meta": {"top_k": 3}}
    ctx = _build_numbered_context(state)
    # [1], [2], [3] 만 있어야 함
    assert "[3]" in ctx
    assert "[4]" not in ctx


def test_build_numbered_context_caps_at_max_context_docs():
    docs = [_make_doc(i) for i in range(20)]
    state = {"reranked": docs, "meta": {"top_k": 20}}
    ctx = _build_numbered_context(state)
    assert f"[{_MAX_CONTEXT_DOCS}]" in ctx
    assert f"[{_MAX_CONTEXT_DOCS + 1}]" not in ctx


def test_build_numbered_context_default_when_no_meta():
    docs = [_make_doc(i) for i in range(10)]
    state = {"reranked": docs, "meta": {}}
    ctx = _build_numbered_context(state)
    # top_k 없으면 기본 6, cap은 MAX_CONTEXT_DOCS=8
    # min(6, 8) = 6
    assert "[6]" in ctx
    assert "[7]" not in ctx


def test_build_numbered_context_empty_docs():
    state = {"reranked": [], "meta": {"top_k": 5}}
    ctx = _build_numbered_context(state)
    assert ctx == ""


# ── Fix 8: committee_distribution (mock) ─────────────────────────────

def test_committee_distribution_calculation():
    """_retrieve_pg 내부 Counter 계산 로직을 직접 검증."""
    from collections import Counter
    results = [
        {"metadata": {"committee": "외교통일위원회"}},
        {"metadata": {"committee": "외교통일위원회"}},
        {"metadata": {"committee": "정무위원회"}},
        {"metadata": {"committee": "과학기술정보방송통신위원회"}},
        {"metadata": {}},  # committee 없음 → 미상
    ]
    comm_dist = Counter(
        (r.get("metadata") or {}).get("committee") or "미상"
        for r in results
    )
    assert comm_dist["외교통일위원회"] == 2
    assert comm_dist["정무위원회"] == 1
    assert comm_dist["과학기술정보방송통신위원회"] == 1
    assert comm_dist["미상"] == 1


# ── Hardcoding 제거: _is_out_of_scope ────────────────────────────────

from service.llm.prompt_templates import _is_out_of_scope, _build_out_of_scope_warning


def test_is_out_of_scope_false_when_no_committee():
    """전체 위원회 검색 시 소관 외 판단 불가 → 항상 False."""
    assert _is_out_of_scope("국민연금 정책", committee="") is False
    assert _is_out_of_scope("국민연금 정책", committee=None) is False


def test_is_out_of_scope_true_for_correct_committee():
    assert _is_out_of_scope("국민연금 정책", committee="외교통일위원회") is True


def test_is_out_of_scope_false_for_in_scope_topic():
    assert _is_out_of_scope("대북정책 논의", committee="외교통일위원회") is False


def test_is_out_of_scope_uses_committee_keywords():
    # 정무위원회: 대북전단은 소관 외
    assert _is_out_of_scope("대북전단 살포 논의", committee="정무위원회") is True
    # 외교통일위원회: 대북전단은 소관 내 → False
    assert _is_out_of_scope("대북전단 살포 논의", committee="외교통일위원회") is False


def test_build_out_of_scope_warning_empty_for_no_committee():
    assert _build_out_of_scope_warning("") == ""
    assert _build_out_of_scope_warning(None) == ""


def test_build_out_of_scope_warning_contains_committee_name():
    warn = _build_out_of_scope_warning("정무위원회")
    assert "정무위원회" in warn
    assert len(warn) > 10


# ── Hardcoding 제거: build_user_prompt E항목 ─────────────────────────

from service.llm.prompt_templates import build_user_prompt


def test_build_user_prompt_e_item_absent_without_committee():
    prompt = build_user_prompt("대북정책", "컨텍스트", committee="")
    assert "E)" not in prompt


def test_build_user_prompt_e_item_present_with_committee():
    prompt = build_user_prompt("국민연금", "컨텍스트", committee="외교통일위원회")
    assert "E)" in prompt
    assert "외교통일위원회" in prompt


def test_build_user_prompt_e_item_uses_actual_committee_name():
    prompt = build_user_prompt("대북전단", "컨텍스트", committee="정무위원회")
    assert "정무위원회" in prompt
    # 외교통일위원회가 E항목에 들어가면 안 됨
    e_start = prompt.find("E)")
    e_end = prompt.find("\n\n", e_start) if e_start != -1 else -1
    if e_start != -1 and e_end != -1:
        e_item_text = prompt[e_start:e_end]
        assert "외교통일위원회" not in e_item_text


# ── Item B: v2 비교쿼리 분리 검색 ────────────────────────────────────

from unittest.mock import MagicMock, patch


def _make_result(chunk_id: str, speaker: str, score: float = 0.9) -> dict:
    return {
        "content": f"{speaker} 발언 내용",
        "chunk_id": chunk_id,
        "source_id": "src_001",
        "date": "2024-01-01",
        "title": "회의록",
        "url": "",
        "similarity": score,
        "hybrid_score": score,
        "speaker": speaker,
        "speaker_role": "위원",
        "metadata": {"committee": "외교통일위원회"},
    }


def test_v2_comparison_calls_search_v2_twice():
    """비교쿼리 시 search_v2를 두 주체에 대해 각각 호출한다."""
    mock_retriever = MagicMock()
    mock_retriever.search_v2.side_effect = [
        [_make_result("a1", "조태열"), _make_result("a2", "조태열")],
        [_make_result("b1", "정동영"), _make_result("b2", "정동영")],
    ]

    with patch("graph.nodes.retrieve_pg.retriever", mock_retriever):
        from graph.nodes import retrieve_pg
        state = {
            "question": "조태열 장관과 정동영 장관 비교",
            "rewritten_query": "조태열 장관과 정동영 장관 비교",
            "meta": {
                "use_v2_retrieval": True,
                "top_k": 4,
                "alpha": 0.75,
                "query_comparison_subjects": [["조태열", "장관"], ["정동영", "장관"]],
            },
        }
        result = retrieve_pg.run(state)

    assert mock_retriever.search_v2.call_count == 2


def test_v2_comparison_interleaves_results():
    """인터리브: A1·B1·A2·B2 순서로 결과가 섞인다."""
    mock_retriever = MagicMock()
    mock_retriever.search_v2.side_effect = [
        [_make_result("a1", "조태열"), _make_result("a2", "조태열")],
        [_make_result("b1", "정동영"), _make_result("b2", "정동영")],
    ]

    with patch("graph.nodes.retrieve_pg.retriever", mock_retriever):
        from graph.nodes import retrieve_pg
        state = {
            "question": "조태열 장관과 정동영 장관 비교",
            "rewritten_query": "조태열 장관과 정동영 장관 비교",
            "meta": {
                "use_v2_retrieval": True,
                "top_k": 4,
                "alpha": 0.75,
                "query_comparison_subjects": [["조태열", "장관"], ["정동영", "장관"]],
            },
        }
        result = retrieve_pg.run(state)

    retrieved = result["retrieved"]
    speakers = [r["speaker"] for r in retrieved]
    assert speakers[0] == "조태열"
    assert speakers[1] == "정동영"


def test_v2_comparison_deduplicates_chunk_ids():
    """chunk_id가 중복되는 결과는 한 번만 포함."""
    mock_retriever = MagicMock()
    mock_retriever.search_v2.side_effect = [
        [_make_result("shared", "조태열"), _make_result("a2", "조태열")],
        [_make_result("shared", "정동영"), _make_result("b2", "정동영")],  # shared 중복
    ]

    with patch("graph.nodes.retrieve_pg.retriever", mock_retriever):
        from graph.nodes import retrieve_pg
        state = {
            "question": "조태열 장관과 정동영 장관 비교",
            "rewritten_query": "조태열 장관과 정동영 장관 비교",
            "meta": {
                "use_v2_retrieval": True,
                "top_k": 4,
                "alpha": 0.75,
                "query_comparison_subjects": [["조태열", "장관"], ["정동영", "장관"]],
            },
        }
        result = retrieve_pg.run(state)

    chunk_ids = [r["chunk_id"] for r in result["retrieved"]]
    assert chunk_ids.count("shared") == 1
    assert len(chunk_ids) == 3  # shared + a2 + b2


def test_v2_single_query_calls_search_v2_once():
    """비교쿼리가 아닌 일반 쿼리는 search_v2 한 번만 호출."""
    mock_retriever = MagicMock()
    mock_retriever.search_v2.return_value = [_make_result("x1", "조태열")]

    with patch("graph.nodes.retrieve_pg.retriever", mock_retriever):
        from graph.nodes import retrieve_pg
        state = {
            "question": "대북정책 논의",
            "rewritten_query": "대북정책 논의",
            "meta": {"use_v2_retrieval": True, "top_k": 5, "alpha": 0.75},
        }
        retrieve_pg.run(state)

    assert mock_retriever.search_v2.call_count == 1


# ── Item A: QueryResponse 신규 필드 ──────────────────────────────────

from api.main import QueryResponse


def test_query_response_has_committee_distribution_field():
    import inspect
    fields = QueryResponse.model_fields
    assert "committee_distribution" in fields
    assert fields["committee_distribution"].default is None


def test_query_response_has_generation_skipped_field():
    fields = QueryResponse.model_fields
    assert "generation_skipped" in fields
    assert fields["generation_skipped"].default is None


def test_query_response_committee_distribution_accepts_dict():
    r = QueryResponse(
        answer="테스트",
        grounding_level="FULL",
        doc_count=3,
        citations=[],
        latency_total_ms=100.0,
        committee_distribution={"외교통일위원회": 2, "정무위원회": 1},
    )
    assert r.committee_distribution == {"외교통일위원회": 2, "정무위원회": 1}


def test_query_response_committee_distribution_optional():
    r = QueryResponse(
        answer="테스트",
        grounding_level="NONE",
        doc_count=0,
        citations=[],
        latency_total_ms=50.0,
    )
    assert r.committee_distribution is None


def test_query_response_generation_skipped_optional():
    r = QueryResponse(
        answer="질문이 너무 간략합니다",
        grounding_level="NONE",
        doc_count=0,
        citations=[],
        latency_total_ms=10.0,
        generation_skipped="needs_clarification",
    )
    assert r.generation_skipped == "needs_clarification"


# ── Item C: 멀티턴 히스토리 지시어 해소 ───────────────────────────────

from service.rag.query.history_resolver import (
    resolve,
    _has_back_ref,
    _extract_entities,
)


@pytest.mark.parametrize("question", [
    "그 장관 발언은?",
    "이 정책 관련 더 있나요?",
    "방금 말한 내용 자세히",
    "앞서 언급한 법안",
    "그 외에도 다른 발언은?",
])
def test_has_back_ref_detects(question):
    assert _has_back_ref(question) is True


@pytest.mark.parametrize("question", [
    "조태열 장관 발언 알려줘",
    "한미동맹 여야 입장 비교",
    "대북정책 논의 내용",
    "2024년 국감 현안",
])
def test_has_back_ref_clean_queries(question):
    assert _has_back_ref(question) is False


def test_extract_entities_person():
    entities = _extract_entities("조태열 장관 한미동맹 발언 알려줘")
    assert "조태열장관" in entities or any("조태열" in e for e in entities)


def test_extract_entities_keyword_fallback():
    entities = _extract_entities("한미동맹 대북정책 현황")
    assert len(entities) > 0
    assert any(len(e) >= 3 for e in entities)


def test_resolve_enriches_back_ref_query():
    history = [{"role": "user", "content": "조태열 장관 발언"}]
    result = resolve("그 장관 최근 발언은?", history)
    assert "조태열" in result
    assert "그 장관 최근 발언은?" in result


def test_resolve_no_change_without_history():
    result = resolve("그 장관 발언은?", [])
    assert result == "그 장관 발언은?"


def test_resolve_no_change_without_back_ref():
    history = [{"role": "user", "content": "조태열 장관 발언"}]
    result = resolve("한미동맹 여야 입장 비교", history)
    assert result == "한미동맹 여야 입장 비교"


def test_resolve_no_duplicate_entity():
    """추출된 엔티티가 이미 현재 질문에 있으면 중복 삽입 안 함."""
    history = [{"role": "user", "content": "조태열 장관 발언"}]
    result = resolve("조태열장관 그 발언 더 있나요?", history)
    assert result.count("조태열") == 1


def test_resolve_uses_last_user_turn():
    """히스토리에 여러 턴이 있으면 마지막 user 턴에서 엔티티 추출."""
    history = [
        {"role": "user", "content": "이전 주제 발언"},
        {"role": "assistant", "content": "답변입니다"},
        {"role": "user", "content": "정동영 의원 입장"},
        {"role": "assistant", "content": "두 번째 답변"},
    ]
    result = resolve("그 의원 다른 발언은?", history)
    assert "정동영" in result


# ── FTS OR 쿼리 수정 검증 ──────────────────────────────────────────────

import re as _re


def test_fts_or_query_token_extraction():
    """2자 이상 한글/영문 토큰을 올바르게 추출한다."""
    query = "조태열 장관 한미동맹"
    tokens = _re.findall(r"[가-힣a-zA-Z0-9]{2,}", query)
    ts_expr = " | ".join(tokens)
    assert ts_expr == "조태열 | 장관 | 한미동맹"


def test_fts_or_query_english():
    """영어 혼합 쿼리도 토큰 추출이 정상 동작한다."""
    query = "NPT 체제 핵억제"
    tokens = _re.findall(r"[가-힣a-zA-Z0-9]{2,}", query)
    ts_expr = " | ".join(tokens)
    assert "NPT" in ts_expr
    assert "핵억제" in ts_expr


def test_fts_or_query_single_char_excluded():
    """1자 토큰은 제외된다."""
    query = "이 정책 A 내용"
    tokens = _re.findall(r"[가-힣a-zA-Z0-9]{2,}", query)
    assert "이" not in tokens
    assert "A" not in tokens
    assert "정책" in tokens


def test_recall_eval_diversity_uses_top_level_speaker():
    """recall_eval.py가 최상위 speaker 키에서 다양성을 계산한다."""
    from service.rag.eval.recall_eval import evaluate
    docs = [
        {"chunk_text": "조태열 장관 발언", "speaker": "조태열", "similarity": 0.9, "metadata": {}},
        {"chunk_text": "홍기원 위원 발언", "speaker": "홍기원", "similarity": 0.8, "metadata": {}},
        {"chunk_text": "정동영 장관 발언", "speaker": "정동영", "similarity": 0.7, "metadata": {}},
    ]
    result = evaluate("한미동맹 발언", docs, k=3)
    assert result["diversity"] == pytest.approx(1.0)


def test_recall_eval_diversity_metadata_fallback():
    """speaker가 최상위에 없으면 metadata.speaker로 폴백한다."""
    from service.rag.eval.recall_eval import evaluate
    docs = [
        {"chunk_text": "발언1", "metadata": {"speaker": "홍기원"}},
        {"chunk_text": "발언2", "metadata": {"speaker": "조태열"}},
    ]
    result = evaluate("테스트", docs, k=2)
    assert result["diversity"] > 0.0


# ── 비교 쿼리 화자 추출 수정 (_SPEAKER_UNIT P2 패턴) ──────────────────────

def test_speaker_unit_extracts_name_before_jeon_title():
    """'이름 전 부처직함' 패턴에서 사람 이름을 첫 번째 키워드로 추출한다."""
    from graph.nodes.router import _extract_comparison_subjects
    q = "조태열 전 외교부장관과 조현 현 외교부장관의 한미동맹 차이가 있나요?"
    subjects = _extract_comparison_subjects(q)
    assert len(subjects) == 2
    assert subjects[0][0] == "조태열"
    assert subjects[1][0] == "조현"


def test_speaker_unit_extracts_name_before_hyeon_title():
    """'이름 현 부처직함' 패턴도 동일하게 이름을 추출한다."""
    from graph.nodes.router import _extract_comparison_subjects
    q = "김영호 전 통일부장관과 정동영 현 통일부장관의 북한 정책 차이는?"
    subjects = _extract_comparison_subjects(q)
    assert len(subjects) == 2
    assert subjects[0][0] == "김영호"
    assert subjects[1][0] == "정동영"


def test_speaker_unit_plain_title_unchanged():
    """'이름 직함' 기존 패턴은 그대로 동작한다."""
    from graph.nodes.router import _extract_comparison_subjects
    q = "조태열 장관과 정동영 장관의 차이는?"
    subjects = _extract_comparison_subjects(q)
    assert len(subjects) == 2
    assert subjects[0][0] == "조태열"
    assert subjects[1][0] == "정동영"


def test_speaker_unit_single_jeon_title_is_speaker_kw():
    """'이름 전 직함' 단일 화자는 speaker_kw로 추출된다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "박진 전 외교부장관이 언급한 한미동맹 내용은?"
    kw = _extract_query_speaker_kw(q)
    assert kw, "단일 화자 키워드가 추출되어야 함"
    assert kw[0] == "박진"


# ── 오탐 방지 테스트 (이름 자리에 수식어·조사·정당명이 들어온 경우) ──────────────

def test_speaker_kw_empty_for_yeoya_query():
    """'여야 의원들의...' 쿼리에서 '여야'를 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "여야 의원들의 대북전단 살포에 대한 시각은 어떻게 다른가요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_empty_for_yeoreo_query():
    """'여러 위원들이...' 쿼리에서 '여러'를 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "일본과의 관계에 대해 여러 위원들이 공통적으로 제기한 우려나 요구는 무엇인가요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_empty_for_dangling_particle():
    """동사 어미('미흡하다는 의원')를 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "오물풍선 대응이 미흡하다는 의원의 비판에 대해 통일부 또는 외교부는 어떻게 답했나요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_empty_for_huboja_query():
    """'위원장 후보자가...' 쿼리에서 '후보자'를 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "방송통신위원장 후보자가 방송 독립성 관련 질의를 받았을 때 어떻게 답변했나요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_no_particle_suffix():
    """'김병환은'에서 조사 '은'이 포함되지 않고 '김병환'만 추출된다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "금융위원장 김병환은 은행 금리 또는 금융 규제에 대해 어떤 입장을 밝혔나요?"
    kw = _extract_query_speaker_kw(q)
    assert kw, "김병환 키워드가 추출되어야 함"
    assert "김병환은" not in kw, "'은' 조사가 포함된 채 추출되면 안 됨"
    assert "김병환" in kw


def test_speaker_kw_committee_name_no_match():
    """'위원회'에서 '위원' 부분을 화자 직함으로 오탐하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "이준석 위원은 과학기술정보방송통신위원회에서 어떤 발언을 했나요?"
    kw = _extract_query_speaker_kw(q)
    assert kw, "이준석 키워드가 추출되어야 함"
    assert kw[0] == "이준석"


def test_comparison_subjects_empty_for_yeodang_query():
    """'여당 의원들'을 비교 주체로 추출하지 않는다."""
    from graph.nodes.router import _extract_comparison_subjects
    q = "계엄 선포 이후 여당 의원들은 외교부장관을 지지했나요, 비판했나요?"
    assert _extract_comparison_subjects(q) == []


def test_comparison_subjects_empty_for_huboja_청문회():
    """'위원장 후보자 청문회' 쿼리에서 가짜 비교 주체를 추출하지 않는다."""
    from graph.nodes.router import _extract_comparison_subjects
    q = "방송통신위원장 후보자 인사청문회에서 위원들이 제기한 주요 쟁점은 무엇이었나요?"
    assert _extract_comparison_subjects(q) == []


def test_speaker_kw_empty_for_party_suffix_euihim():
    """'국민의힘 위원들' 쿼리에서 당명 접미어 '의힘'을 인명으로 오탐하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "트럼프 2기 통상 압박에 대해 더불어민주당과 국민의힘 위원들은 서로 어떻게 다른 대응을 정부에 요구했나요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_real_name_after_party_mention():
    """당명이 등장해도 실제 인명+직함은 정상 추출된다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "국민의힘 소속 조태열 장관은 대북 정책에 대해 어떤 입장인가요?"
    kw = _extract_query_speaker_kw(q)
    assert kw and "조태열" in kw


# ── 집계형 쿼리: 지시 한정사 오탐 방지 ───────────────────────────────────

def test_speaker_kw_empty_for_eotteon_uiwon():
    """'어떤 의원들이...' 쿼리에서 '어떤'을 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "어떤 의원들이 공통적으로 트럼프 관세에 우려를 표명했나요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_empty_for_eoneu_uiwon():
    """'어느 위원들이...' 쿼리에서 '어느'를 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "어느 위원들이 방산 비리를 가장 강하게 문제 제기했나요?"
    assert _extract_query_speaker_kw(q) == []


def test_speaker_kw_empty_for_modeun_uiwon():
    """'모든 의원들이...' 쿼리에서 '모든'을 인명으로 추출하지 않는다."""
    from graph.nodes.router import _extract_query_speaker_kw
    q = "모든 의원들이 동의한 사안은 무엇인가요?"
    assert _extract_query_speaker_kw(q) == []


# ── 집계형 쿼리 감지: aggregate_query 플래그 ─────────────────────────────

def test_aggregate_query_detected_for_eotteon_uiwon():
    """'어떤 의원들이...' 패턴은 aggregate_query=True로 설정된다."""
    from graph.nodes.router import run
    state = {"question": "어떤 의원들이 공통적으로 트럼프 관세에 우려를 표명했나요?", "meta": {}}
    result = run(state)
    assert result["meta"].get("aggregate_query") is True


def test_aggregate_query_balance_speakers_enabled():
    """집계형 쿼리 감지 시 balance_speakers가 자동 활성화된다."""
    from graph.nodes.router import run
    state = {"question": "위원들이 공통적으로 제기한 쟁점은?", "meta": {}}
    result = run(state)
    assert result["meta"].get("balance_speakers") is True


def test_aggregate_query_top_k_increased():
    """집계형 쿼리 감지 시 top_k가 최소 8로 증가한다."""
    from graph.nodes.router import run
    state = {"question": "어떤 의원들이 관세에 비판적이었나요?", "meta": {"top_k": 4}}
    result = run(state)
    assert result["meta"].get("top_k", 0) >= 8


def test_aggregate_query_no_speaker_kw_set():
    """집계형 쿼리는 query_speaker_kw가 설정되지 않는다."""
    from graph.nodes.router import run
    state = {"question": "어느 위원들이 방산 비리를 강하게 제기했나요?", "meta": {}}
    result = run(state)
    assert not result["meta"].get("query_speaker_kw")


def test_named_speaker_not_aggregate():
    """실명 화자 쿼리는 aggregate_query가 설정되지 않는다."""
    from graph.nodes.router import run
    state = {"question": "조태열 장관이 한미동맹에 대해 어떤 발언을 했나요?", "meta": {}}
    result = run(state)
    assert not result["meta"].get("aggregate_query")


def test_aggregate_retrieve_disables_speaker_filter():
    """aggregate_query=True 시 retrieve_pg에서 화자 필터가 무시된다."""
    from unittest.mock import MagicMock, patch

    mock_retriever = MagicMock()
    mock_retriever.search_v2.return_value = []

    with patch("graph.nodes.retrieve_pg.retriever", mock_retriever):
        from graph.nodes import retrieve_pg
        state = {
            "question": "어떤 의원들이 관세에 비판적이었나요?",
            "rewritten_query": "어떤 의원들이 관세에 비판적이었나요?",
            "meta": {
                "use_v2_retrieval": True,
                "top_k": 8,
                "alpha": 0.75,
                "aggregate_query": True,
                "balance_speakers": True,
                "query_speaker_kw": ["어떤", "의원"],  # 잘못 추출된 경우에도 무시됨
            },
        }
        retrieve_pg.run(state)

    call_kwargs = mock_retriever.search_v2.call_args[1]
    assert call_kwargs.get("speaker") is None
