import re
import time

from graph.state import QAState
from service.rag.retrieval.date_range import normalize_meeting_date_range
from service.rag.retrieval.retriever import Retriever
from service.rag.models.config import EmbeddingModelType

import streamlit as st

# ── 청크 오염 제거 패턴 ───────────────────────────────────────────
# 1) 의장 호명: "○○위원 발언해 주십시오" 류
_CHAIR_CALL = re.compile(
    r"[^\n]*(?:발언해|질의해|답변해)\s*(?:주십시오|주시기\s*바랍니다)[^\n]*\n?",
    re.MULTILINE,
)
# 2) 회의 메타데이터: "제NNN회 ○○위원회NN차(YYYY년N월N일) P " 형태
#    [^\n]*?에서 .*) 뒤 페이지 번호 + 공백까지만 제거 → 이후 실제 발언 내용 보존
_MEETING_META = re.compile(
    r"제\d+회[가-힣()·\s\d]*?\d{4}[년가-힣\d월일\s]*\)\s*\d+\s+",
)
# 3) 의례적 인사말 줄: "수고하셨습니다", "감사합니다" 단독 줄
# $ 대신 (?:\n|$)를 명시 — MULTILINE에서 \s*$가 \n을 삼켜 매칭 실패하는 케이스 방지
_COURTESY = re.compile(
    r"[ \t]*(?:수고하셨습니다|감사합니다|이상입니다|마치겠습니다)[.!]?[ \t]*(?:\n|$)",
    re.MULTILINE,
)
# 4) 페이지 연속 마커: "계속해서 N쪽입니다", "다음 N쪽입니다" 등
_PAGE_CONT = re.compile(r"계속해서\s*\d+쪽입니다[.。]?\s*|다음\s*\d+쪽입니다[.。]?\s*")
# 5) 문장 종결 패턴
_SENT_END = re.compile(r"[다요입함됩니겠었했죠네음][.!?…]")
# 6) 접속사·연결어로 시작하는 dangling head 패턴
_CONJUNCTION_START = re.compile(
    r"^(?:그래서|따라서|그러나|그런데|그리고|또한|또|아울러|한편|이에|이와|이는|이처럼|"
    r"이러한|이런|이와 같이|즉|결국|다만|물론|특히|뿐만 아니라|더불어|반면|오히려|"
    r"하지만|그렇지만|때문에|으로 인해|로 인해)[,\s]"
)


def _trim_dangling_head(text: str, max_head: int = 100) -> str:
    """청크가 문장 중간·접속사에서 시작하면 첫 완전 문장 이후부터 반환."""
    # 접속사/연결어 시작 → 첫 문장 종결까지 건너뜀
    if _CONJUNCTION_START.match(text):
        m = _SENT_END.search(text[:200])
        if m:
            remainder = text[m.end():].lstrip(" 　")
            if len(remainder) >= 40:
                return remainder

    # 문장 중간 시작 (앞부분에서 종결어미 발견)
    head = text[:max_head]
    m = _SENT_END.search(head)
    if m:
        cut = m.end()
        remainder = text[cut:].lstrip(" 　")
        if len(remainder) >= 40:
            return remainder
    return text


def _restore_pdf_linebreaks(text: str) -> str:
    """PDF 추출 시 생긴 인위적 줄바꿈 복원.
    - 단어 중간 분리(이전 줄이 모음·조사로 끝남): 공백 없이 이어붙임
    - 문장 내 줄바꿈: 공백으로 이어붙임
    - 문장 종결 후 줄바꿈: 줄바꿈 유지
    """
    # 단어 중간에서 잘리는 경우의 마지막 음절 패턴 (으, 이, 아, 에 등 중간 모음)
    _MID_WORD = re.compile(r"[으이아에오우위의]$")
    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if not stripped:
            out.append("\n")
            continue
        if i < len(lines) - 1:
            last_char = stripped[-1]
            if last_char in ".!?…。":
                # 문장 종결 → 줄바꿈 유지
                out.append(stripped + "\n")
            elif _MID_WORD.search(stripped):
                # 단어 중간 분리 → 공백 없이 이어붙임
                out.append(stripped)
            else:
                # 문장 내 줄바꿈 → 공백으로 이어붙임
                out.append(stripped + " ")
        else:
            out.append(stripped)
    return "".join(out).strip()


def _clean_chunk(text: str) -> str:
    """DB에서 가져온 청크의 오염 텍스트 제거 (ETL 재실행 전 임시 보정)."""
    t = _CHAIR_CALL.sub("", text)
    t = _MEETING_META.sub("", t)
    t = _COURTESY.sub("", t)
    t = _PAGE_CONT.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) < 20:
        return text.strip()
    t = _restore_pdf_linebreaks(t)
    t = _trim_dangling_head(t)
    return t

retriever = Retriever(model_type=EmbeddingModelType.MULTILINGUAL_E5_SMALL, enable_temporal_filter=False)


def run(state: QAState) -> QAState:
    _t_retrieve_start = time.perf_counter()
    query = state.get("rewritten_query") or state.get("question", "")
    meta = state.get("meta") or {}
    top_k = int(meta.get("top_k", 5))
    alpha = float(meta.get("alpha", 0.8))
    committee_raw = meta.get("committee")
    committee = (str(committee_raw).strip() if committee_raw is not None else "") or None
    date_from = meta.get("date_from") or None
    date_to = meta.get("date_to") or None
    if isinstance(date_from, str) and not date_from.strip():
        date_from = None
    if isinstance(date_to, str) and not date_to.strip():
        date_to = None
    date_from, date_to = normalize_meeting_date_range(
        str(date_from) if date_from else None,
        str(date_to) if date_to else None,
    )
    use_reranker = bool(meta.get("use_reranker", False))
    balance_speakers = bool(meta.get("balance_speakers", False))
    candidate_multiplier = int(meta.get("candidate_multiplier", 50))
    use_multi_query = bool(meta.get("use_multi_query", False))
    multi_query_variants = int(meta.get("multi_query_variants", 3))
    use_hyde = bool(meta.get("use_hyde", False))
    use_parent_doc = bool(meta.get("use_parent_doc", False))
    parent_doc_window = int(meta.get("parent_doc_window", 1))
    use_compression = bool(meta.get("use_compression", False))
    use_step_back = bool(meta.get("use_step_back", False))
    use_fusion = bool(meta.get("use_fusion", False))
    use_neural_reranker = bool(meta.get("use_neural_reranker", False))
    use_llm_reranker = bool(meta.get("use_llm_reranker", False))
    use_mmr = bool(meta.get("use_mmr", False))
    mmr_lambda = float(meta.get("mmr_lambda", 0.7))
    use_score_norm = bool(meta.get("use_score_norm", False))
    use_ensemble_reranker = bool(meta.get("use_ensemble_reranker", False))
    eval_recall = bool(meta.get("eval_recall", False))
    use_v2_retrieval = bool(meta.get("use_v2_retrieval", False))

    _search_kwargs = dict(
        alpha=alpha,
        committee=committee,
        date_from=date_from,
        date_to=date_to,
        include_metadata=True,
        use_reranker=use_reranker,
        balance_speakers=balance_speakers,
        candidate_multiplier=candidate_multiplier,
        use_multi_query=use_multi_query,
        multi_query_variants=multi_query_variants,
        use_hyde=use_hyde,
        use_parent_doc=use_parent_doc,
        parent_doc_window=parent_doc_window,
        use_compression=use_compression,
        use_step_back=use_step_back,
        use_fusion=use_fusion,
        use_neural_reranker=use_neural_reranker,
        use_llm_reranker=use_llm_reranker,
        use_mmr=use_mmr,
        mmr_lambda=mmr_lambda,
        use_score_norm=use_score_norm,
        use_ensemble_reranker=use_ensemble_reranker,
        eval_recall=eval_recall,
    )

    # Rule 1: 비교 쿼리는 두 주체 각각 별도 검색 후 병합
    comparison_subjects = meta.get("query_comparison_subjects") or []
    #st.write (comparison_subjects)
    # v2 검색 경로 (use_v2_retrieval=True)
    if use_v2_retrieval:
        if len(comparison_subjects) == 2:
            print("[Retrieve] use_v2_retrieval=True — 비교쿼리 병렬 검색 미지원, 통합 v2 검색으로 대체")
        results = retriever.search_v2(
            query=query,
            top_k=top_k,
            committee=committee,
            date_from=date_from,
            date_to=date_to,
            speaker=meta.get("speaker") or None,
            use_neural_reranker=use_neural_reranker,
        )
    # v1 검색 경로 (기존 로직 완전 유지)
    elif len(comparison_subjects) == 2:
        per_k = max(top_k * 2, 15)
        seen_ids: set[str] = set()
        results = []
        for i, subj_kw in enumerate(comparison_subjects):
            speaker_name = subj_kw[0]
            other_name = comparison_subjects[1 - i][0]
            topic_query = query.replace(other_name, "")
            topic_query = re.sub(r'\s+', ' ', topic_query).strip()
            subj_query = " ".join(subj_kw) + " " + topic_query
            subj_results = retriever.search(query=subj_query, top_k=per_k, speaker=speaker_name, **_search_kwargs)
            for r in subj_results:
                cid = r.get("chunk_id") or r.get("source_id") or ""
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    results.append(r)
        print(f"[Retrieve] 비교쿼리 분리 검색: {len(results)}개 병합")
    else:
        results = retriever.search(query=query, top_k=top_k, **_search_kwargs)
    state["retrieval_empty"] = len(results) == 0
    state["retrieved"] = [
        {
            "chunk_text": _clean_chunk(r.get("content", "")),
            "source_id": r.get("source_id", ""),
            "date": r.get("date", ""),
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "chunk_id": r.get("chunk_id", ""),
            "similarity": r.get("similarity", 0.0),
            "speaker": r.get("speaker", ""),
            "speaker_role": r.get("speaker_role", ""),
            "metadata": r.get("metadata", {}),
        }
        for r in results
    ]

    latency = state.get("latency_ms") or {}
    latency["retrieve_ms"] = round((time.perf_counter() - _t_retrieve_start) * 1000, 1)
    state["latency_ms"] = latency

    return state
