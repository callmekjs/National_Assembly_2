from __future__ import annotations

import base64
import json
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

import pandas as pd
import streamlit as st
from datetime import date, datetime
from service.chat_service import ChatService
from service.llm.llm_client import llm_env_probe
from graph.app_graph import build_app

# 본문과 참고 자료 UI 분리용 마커(모델 출력에 포함되지 않음)
RAG_REF_MARKER = "<!--RAG_REFERENCES-->"
RAG_CITATIONS_JSON_BEGIN = "<!--CITATIONS_JSON-->"
RAG_CITATIONS_JSON_END = "<!--/CITATIONS_JSON-->"

# chat.py → pages/views/chat.py : parents[2] = 프로젝트 루트
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def change_chat_theme() -> None:
    st.markdown("""
    <style>
    div.stButton > button {
        background: #FFFFFF;        /* 흰색 배경 */
        color: #3B82F6;             /* 버튼 글자 색 (예: 파란색) */
        border: 1px solid #E5E7EB;  /* 테두리 약하게 */
        padding: 0.6rem 1.2rem;     
        border-radius: 10px;
        font-weight: 600;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    }
    div.stButton > button:hover {
        background: #F9FAFB;        /* hover 시 살짝 회색톤 */
        border-color: #D1D5DB;
    }
    
    /* 채팅 입력창 스타일 */
    .stChatInput > div > div > div > div {
        border: 2px solid #E5E7EB !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
        transition: all 0.2s ease !important;
    }
    
    .stChatInput > div > div > div > div:focus-within {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1), 0 2px 8px rgba(0,0,0,0.12) !important;
    }
    
    /* 입력창 내부 텍스트 영역 */
    .stChatInput textarea {
        border: 1px solid #D1D5DB !important;
        border-radius: 8px !important;
        outline: none !important;
        padding: 12px 16px !important;
        background: #FFFFFF !important;
        transition: border-color 0.2s ease !important;
    }
    .stChatInput textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1) !important;
    }
    
    /* 전송 버튼 스타일 */
    .stChatInput button {
        background: #3B82F6 !important;
        border: none !important;
        border-radius: 8px !important;
        margin: 4px !important;
    }
    .stChatInput button:hover {
        background: #2563EB !important;
    }

    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] {
        overflow-wrap: anywhere;
        word-break: break-word;
        max-width: 100%;
    }
    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] pre,
    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] code {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }
    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] p {
        margin-bottom: 0.65rem;
        line-height: 1.65;
    }
    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] h2,
    section[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] h3 {
        margin-top: 0.9rem;
        margin-bottom: 0.45rem;
    }
    section[data-testid="stChatMessage"] [data-testid="stExpander"] div[data-testid="stMarkdownContainer"] {
        overflow-wrap: anywhere;
        word-break: break-word;
        max-width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)



# 추천 질문 (난이도 분기 없음 — 단일 고품질 답변 모드)
SUGGESTED_QUESTIONS = [
    "외교통일위원회 최근 회의의 핵심 쟁점과 정책 함의를 정리해줘.",
    "특정 회의록에서 누가 어떤 발언을 했는지 근거와 함께 알려줘.",
    "같은 안건이 여러 회의에서 어떻게 이어졌는지 비교해줘.",
    "쟁점별로 여야·정부 발언 경향을 회의록 근거로 정리해줘.",
    "특정 기간 회의록에서 외교 현안의 논점 변화를 추적해줘.",
    "주요 발언자별 주장 패턴을 근거와 함께 비교해줘.",
]


MAX_HISTORY_TURNS = 3  # LLM에 전달할 이전 Q&A 턴 수

# 채팅 서비스 초기화
chat_service = ChatService()

def render_chat_panel() -> None:
    """Render interactive chat interface for Q&A."""
    # 버튼 스타일 적용
    change_chat_theme()

    _llm_setup_banner()

    _init_state()
    
    # 대화창 관리 사이드바를 맨 먼저 렌더링 (상단에 위치)
    _render_sidebar()
    
    # # 현재 대화창 제목 표시
    current_session = st.session_state.chat_sessions[st.session_state.current_session_id]
    current_history = current_session['messages']
    if len(current_history) <= 1:
        _render_suggested_questions()

    st.caption("답변이 출력되면 맨 아래 **참고 자료** 블록에서 출처 번호 `[n]`과 인용 형식을 확인할 수 있습니다.")

    # 채팅 메시지 표시
    chat_container = st.container()
    for mi, message in enumerate(current_history):
        role = message["role"]
        with chat_container:
            with st.chat_message(name=role, avatar=_avatar_for(role)):
                if role == "assistant":
                    _render_assistant_markdown(message["content"], msg_key=str(mi))
                else:
                    st.markdown(message["content"])

    # 채팅 입력창
    user_input = st.chat_input("질문을 입력하세요.")
    if user_input:
        _handle_user_input(user_input)


def _render_suggested_questions() -> None:
    """예상 질문 버튼들을 렌더링"""
    st.markdown("### 💡 추천 질문")
    st.markdown("궁금한 내용을 클릭해보세요!")
    st.markdown(
        """
        <style>
        .suggested-wrap div[data-testid="column"] div.stButton > button {
            height: 72px !important;
            min-height: 72px !important;
            max-height: 72px !important;
            white-space: normal !important;
            line-height: 1.2 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # 2열로 버튼 배치
    st.markdown('<div class="suggested-wrap">', unsafe_allow_html=True)
    cols = st.columns(2)
    questions = SUGGESTED_QUESTIONS
    for i, question in enumerate(questions):
        col = cols[i % 2]
        with col:
            if st.button(question, key=f"suggested_q_{i}", use_container_width=True):
                _handle_user_input(question)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()


def _init_state() -> None:
    """세션 상태 초기화"""
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
        st.session_state.current_session_id = None
        _load_saved_sessions()
    defaults = [
        ("qa_top_k", 8),
        ("qa_alpha", 0.75),
        ("qa_candidate_multiplier", 50),
        ("qa_use_reranker", False),
        ("qa_balance_speakers", False),
        ("qa_use_multi_query", False),
        ("qa_use_hyde", False),
        ("qa_use_step_back", False),
        ("qa_use_fusion", True),
        ("qa_use_parent_doc", False),
        ("qa_use_compression", False),
        ("qa_use_neural_reranker", True),
        ("qa_use_llm_reranker", False),
        ("qa_use_mmr", False),
        ("qa_mmr_lambda", 0.7),
        ("qa_use_score_norm", False),
        ("qa_use_ensemble_reranker", False),
        ("qa_eval_recall", False),
    ]
    for key, val in defaults:
        if key not in st.session_state:
            st.session_state[key] = val
    if "qa_committee" not in st.session_state:
        st.session_state.qa_committee = "외교통일위원회"
    if "qa_date_from" not in st.session_state:
        st.session_state.qa_date_from = ""
    if "qa_date_to" not in st.session_state:
        st.session_state.qa_date_to = ""
    if not st.session_state.current_session_id or st.session_state.current_session_id not in st.session_state.chat_sessions:
        _create_new_session()


def _build_search_meta_from_session() -> dict:
    return {
        "top_k": int(st.session_state.get("qa_top_k", 8)),
        "alpha": float(st.session_state.get("qa_alpha", 0.75)),
        "committee": str(st.session_state.get("qa_committee", "") or "").strip(),
        "date_from": str(st.session_state.get("qa_date_from", "") or "").strip(),
        "date_to": str(st.session_state.get("qa_date_to", "") or "").strip(),
        "use_reranker": bool(st.session_state.get("qa_use_reranker", False)),
        "balance_speakers": bool(st.session_state.get("qa_balance_speakers", False)),
        "candidate_multiplier": int(st.session_state.get("qa_candidate_multiplier", 50)),
        "use_multi_query": bool(st.session_state.get("qa_use_multi_query", False)),
        "use_hyde": bool(st.session_state.get("qa_use_hyde", False)),
        "use_step_back": bool(st.session_state.get("qa_use_step_back", False)),
        "use_fusion": bool(st.session_state.get("qa_use_fusion", False)),
        "use_parent_doc": bool(st.session_state.get("qa_use_parent_doc", False)),
        "use_compression": bool(st.session_state.get("qa_use_compression", False)),
        "use_neural_reranker": bool(st.session_state.get("qa_use_neural_reranker", False)),
        "use_llm_reranker": bool(st.session_state.get("qa_use_llm_reranker", False)),
        "use_mmr": bool(st.session_state.get("qa_use_mmr", False)),
        "mmr_lambda": float(st.session_state.get("qa_mmr_lambda", 0.7)),
        "use_score_norm": bool(st.session_state.get("qa_use_score_norm", False)),
        "use_ensemble_reranker": bool(st.session_state.get("qa_use_ensemble_reranker", False)),
        "eval_recall": bool(st.session_state.get("qa_eval_recall", False)),
        "use_v2_retrieval": True,
    }


def _format_user_error(exc: BaseException) -> tuple[str, str]:
    """(사용자용 짧은 메시지, 상세/재시도 안내)"""
    raw = str(exc).strip()
    lower = raw.lower()
    if "connection refused" in lower or "could not connect" in lower:
        return (
            "데이터베이스에 연결할 수 없습니다.",
            "Docker Postgres가 실행 중인지 확인하세요. Windows에서는 `PG_PORT=5433`이 맞는지 확인한 뒤 같은 질문을 다시 보내 보세요.",
        )
    if "embeddings_e5" in lower and ("does not exist" in lower or "undefinedtable" in lower):
        return (
            "벡터 테이블이 없거나 다른 DB에 연결된 상태입니다.",
            "`python -m service.etl.loader.loader_cli load doc …` 후 `load vector`를 실행했는지, `PG_PORT`가 프로젝트 DB 포트와 같은지 확인하세요. 자세한 내용은 저장소의 `OPERATIONS.md`를 참고하세요.",
        )
    if "operationalerror" in lower or "psycopg2" in lower:
        return (
            "DB 작업 중 오류가 발생했습니다.",
            "포트·비밀번호·DB 이름이 맞는지 확인하고, 잠시 후 다시 시도하세요.",
        )
    return (
        "답변을 준비하는 중 문제가 발생했습니다.",
        f"재시도: 같은 질문을 한 번 더 보내 보세요. 문제가 계속되면 페이지를 새로고침(F5) 후 다시 시도하세요.",
    )


def _render_sidebar() -> None:
    """대화 및 검색 설정 사이드바"""
    with st.sidebar:
        with st.expander("검색·답변 설정", expanded=True):
            st.slider(
                "검색 문서 개수 (top-k)",
                min_value=3,
                max_value=20,
                key="qa_top_k",
                help="한 번에 가져올 유사 회의록 청크 수입니다.",
            )
            st.slider(
                "벡터·키워드 가중치",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="qa_alpha",
                help="1에 가까울수록 벡터 유사도 비중이 큽니다.",
            )
            st.text_input(
                "위원회 필터 (정확히 일치)",
                key="qa_committee",
                placeholder="예: 외교통일위원회",
                help="비우면 위원회 필터 없이 검색합니다.",
            )
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("회의일 시작", key="qa_date_from", placeholder="YYYY-MM-DD")
            with c2:
                st.text_input("회의일 종료", key="qa_date_to", placeholder="YYYY-MM-DD")
            st.checkbox(
                "재순위화(rerank) 사용",
                key="qa_use_reranker",
                help="켜면 일부 회의청크가 순위에서 밀릴 수 있습니다. 회귀 평가·특정 날 일정 회의 검색에는 끔을 권장합니다.",
            )
            st.checkbox(
                "발언자 균형",
                key="qa_balance_speakers",
                help="발언자를 골고루 섞으며, 순위 재배열로 관련 청크가 밀릴 수 있습니다.",
            )
            st.number_input(
                "초기 후보 배수",
                min_value=1,
                max_value=80,
                key="qa_candidate_multiplier",
                help="벡터 검색 초기 후보를 top-k×배수만큼 넓힌 뒤 하이브리드로 줄입니다. 긴 회의·후반 청크는 값이 너무 작으면 누락됩니다.",
            )

        with st.sidebar.expander("고급 검색 전략", expanded=False):
            st.caption("각 전략은 독립적으로 켜고 끌 수 있어요. LLM 호출이 있는 항목은 응답 시간이 늘어납니다.")
            st.checkbox(
                "Multi-query Retrieval",
                key="qa_use_multi_query",
                help="질문을 3개로 변형해 각각 검색 후 RRF 통합 (LLM 호출)",
            )
            st.checkbox(
                "HyDE (가상 답변 임베딩)",
                key="qa_use_hyde",
                help="LLM이 가상 답변 생성 → 그 임베딩으로 검색 (LLM 호출)",
            )
            st.checkbox(
                "Step-back Prompting",
                key="qa_use_step_back",
                help="구체 질문 → 추상 질문으로 변환 후 검색, 결과 RRF 통합 (LLM 호출)",
            )
            st.checkbox(
                "Fusion Retrieval (BM25+벡터 RRF)",
                key="qa_use_fusion",
                help="벡터 검색 + BM25 재정렬 결과를 RRF로 통합",
            )
            st.checkbox(
                "Parent Document 확장",
                key="qa_use_parent_doc",
                help="검색된 청크 앞뒤 1개 청크까지 포함해 더 넓은 문맥 전달",
            )
            st.checkbox(
                "Contextual Compression",
                key="qa_use_compression",
                help="검색 청크에서 질문 무관 문장 제거 (LLM 호출, 토큰 절감)",
            )
            st.divider()
            st.checkbox(
                "Neural Reranker (Cross-Encoder)",
                key="qa_use_neural_reranker",
                help="BAAI/bge-reranker-v2-m3 모델로 질문-청크 쌍 정밀 재정렬 (첫 실행 시 모델 다운로드 ~570MB, 이후 빠름)",
            )
            st.checkbox(
                "LLM Reranker",
                key="qa_use_llm_reranker",
                help="GPT-4o-mini가 후보 10개를 보고 관련도 순서로 재정렬 (LLM 호출, 모델 불필요)",
            )
            st.checkbox(
                "MMR (다양성 재정렬)",
                key="qa_use_mmr",
                help="관련도 유지하면서 중복 청크 제거 — 같은 발언자·주제 반복을 줄임 (λ=0.7)",
            )
            st.checkbox(
                "Score Normalization",
                key="qa_use_score_norm",
                help="벡터·어휘·키워드 점수를 min-max 정규화 후 앙상블 — 점수 편향 완화",
            )
            st.checkbox(
                "Ensemble Reranker (Neural+LLM RRF)",
                key="qa_use_ensemble_reranker",
                help="Neural + LLM 두 재정렬기를 독립 실행 후 RRF 합산 — 단독보다 안정적 (LLM 호출 + 모델 로드)",
            )
            st.divider()
            st.checkbox(
                "recall@3 지표 출력 (서버 로그)",
                key="qa_eval_recall",
                help="검색마다 keyword_hit_rate / diversity / avg_similarity를 서버 콘솔에 출력",
            )

        st.markdown("## 💬 대화창 관리")
        
        # 기존 대화 목록
        if st.session_state.chat_sessions:
            for session_id, session in st.session_state.chat_sessions.items():
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button(
                        f"{'🔊' if session_id == st.session_state.current_session_id else ' '} {session['title'][:20]}...",
                        key=f"session_{session_id}",
                        width='stretch'
                    ):
                        st.session_state.current_session_id = session_id
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"delete_{session_id}", help="대화 삭제"):
                        _delete_session(session_id)
                        st.rerun()

        # 새 대화 버튼
        if st.button("➕ 새 대화", width='stretch'):
            _create_new_session()
            st.rerun()
        st.markdown("---")
        st.caption("© 2025 SKN18-3rd-5Team")


def _create_new_session() -> None:
    """새 대화 세션 생성"""
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    title = f"대화 {len(st.session_state.chat_sessions) + 1}"
    if chat_service.create_session(session_id, title):
        chat_service.add_message(
            session_id,
            "assistant",
                "안녕하세요! 왼쪽에서 검색 범위(위원회·날짜 등)를 조정한 뒤, 아래에 질문을 입력해 주세요. 답변 맨 아래에 참고 자료가 붙습니다."
        )
        
        # 세션 상태에 추가
        st.session_state.chat_sessions[session_id] = {
            "title": title,
            "created_at": datetime.now().isoformat(),
            "messages": [
                {
                    "role": "assistant",
                    "content": "안녕하세요! 왼쪽에서 검색 범위(위원회·날짜 등)를 조정한 뒤, 아래에 질문을 입력해 주세요. 답변 맨 아래에 참고 자료가 붙습니다.",
                    "timestamp": datetime.now().isoformat()
                }
            ]
        }
        st.session_state.current_session_id = session_id


def _delete_session(session_id: str) -> None:
    """대화 세션 삭제"""
    # SQLite에서 세션 삭제
    if chat_service.delete_session(session_id):
        # 세션 상태에서도 삭제
        if session_id in st.session_state.chat_sessions:
            del st.session_state.chat_sessions[session_id]
        
        # 삭제된 세션이 현재 세션이면 다른 세션으로 변경
        if st.session_state.current_session_id == session_id:
            if st.session_state.chat_sessions:
                st.session_state.current_session_id = list(st.session_state.chat_sessions.keys())[0]
            else:
                _create_new_session()


_HISTORY_STRIP_PREFIXES = (
    "\n\n*⚠",       # _WARN_NONE
    "\n\n*ℹ",       # _WARN_PARTIAL
    "\n\n※ 본 답변은",  # disclaimer
    "\n\n> 🔍",      # _confidence_line
)


def _strip_system_appends(text: str) -> str:
    """히스토리 전달 시 LLM이 모방하지 않도록 시스템이 붙인 경고·메타 문구 제거.
    ## 한계 섹션도 제거 — 코드가 삽입한 *(비교 근거 부족)* 등 노이즈가 포함돼 있어
    LLM이 다음 턴에 이를 모방해 날조가 심화되는 것을 막는다.
    """
    # 한계 섹션 통째로 제거
    for header in ("## 한계\n", "## 한계 \n", "## 한계"):
        idx = text.find(header)
        if idx != -1:
            text = text[:idx]
            break
    for prefix in _HISTORY_STRIP_PREFIXES:
        idx = text.find(prefix)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _build_history() -> list[dict]:
    """현재 세션의 최근 N턴 Q&A를 OpenAI messages 형식으로 반환 (인용 블록·시스템 문구 제거)."""
    session = st.session_state.chat_sessions.get(st.session_state.current_session_id, {})
    msgs = session.get("messages", [])
    # 마지막 1개는 방금 추가된 현재 질문 → 제외
    history_msgs = msgs[:-1]

    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(history_msgs):
        m = history_msgs[i]
        if m["role"] == "user" and i + 1 < len(history_msgs) and history_msgs[i + 1]["role"] == "assistant":
            asst = history_msgs[i + 1]["content"]
            if RAG_REF_MARKER in asst:
                asst = asst[: asst.index(RAG_REF_MARKER)].strip()
            asst = _strip_system_appends(asst)
            pairs.append((m["content"], asst))
            i += 2
        else:
            i += 1

    result: list[dict] = []
    for user_content, asst_content in pairs[-MAX_HISTORY_TURNS:]:
        result.append({"role": "user", "content": user_content})
        result.append({"role": "assistant", "content": asst_content})
    return result


def _confidence_line(
    docs: list[dict],
    grounding_level: str = "",
    committee: str = "",
) -> str:
    """검색 결과 수 + 근거 상태 레이블 한 줄 요약."""
    n = len(docs)
    if not n:
        return ""

    # 근거 상태 레이블 (유사도 숫자 대신 실무 용어)
    level_map = {
        "FULL":    "✅ 근거 충분",
        "PARTIAL": "⚠️ 부분 확인",
        "NONE":    "❌ 근거 부족",
    }
    level_label = level_map.get(grounding_level.upper(), "")

    # 검색 범위
    scope = f"**{committee}**" if committee else "전체 위원회"
    parts = [f"\n\n> 🔍 검색 범위: {scope} · 검토 청크 **{n}개**"]
    if level_label:
        parts.append(f"· 근거 상태: {level_label}")
    return " ".join(parts)


def _handle_user_input(user_input: str) -> None:
    from graph.nodes.generate import build_prompts_from_state, _sanitize_invalid_citations
    from service.llm.llm_client import chat_stream

    _append_message("user", user_input)
    history = _build_history()

    # 이미 렌더된 chat_container 아래에 새 메시지 즉시 표시
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(user_input)

    try:
        app = _get_langgraph_app()
        meta = _build_search_meta_from_session()
        meta["skip_generate"] = True  # Generate 노드 스킵, 여기서 직접 스트리밍

        with st.spinner("회의록을 검색하는 중..."):
            lg_state = app.invoke({"question": user_input, "meta": meta})

        docs = lg_state.get("reranked") or lg_state.get("retrieved") or []
        if not docs:
            reply = _format_langgraph_response(lg_state)
            with st.chat_message("assistant", avatar="🤖"):
                _render_assistant_markdown(reply)
            _append_message("assistant", reply)
        else:
            from graph.nodes.grounding_check import (
                _is_weak_retrieval,
                _fix_out_of_range,
                _move_uncited_to_limits,
                _strip_detail_if_conclusion_refusal,
                _validate_speaker_bullets,
                _remove_contradictory_limits,
                _check_per_subject_grounding,
                _remove_unlabeled_detail_section,
                _grounding_score,
                _pre_normalize,
                CITE_FULL_THRESHOLD,
                _WARN_PARTIAL,
                _WARN_NONE,
                _WARN_SPEAKER_MISMATCH,
                _REFUSAL_WEAK,
            )
            # 기준 5: 약한 검색 결과면 스트리밍 전에 거부
            if _is_weak_retrieval(docs):
                with st.chat_message("assistant", avatar="🤖"):
                    st.warning(_REFUSAL_WEAK)
                _append_message("assistant", _REFUSAL_WEAK)
            else:
                system_prompt, user_prompt = build_prompts_from_state(lg_state)
                with st.chat_message("assistant", avatar="🤖"):
                    streamed_text = st.write_stream(
                        chat_stream(system_prompt, user_prompt, max_tokens=512, history=history)
                    )

                # 기준 2: [n] 범위 검증
                clean_text = _sanitize_invalid_citations(str(streamed_text), len(docs))
                clean_text, _ = _fix_out_of_range(clean_text, len(docs))

                # 핵심 결론 '확인 불가' → 세부 근거 제거
                clean_text, _ = _strip_detail_if_conclusion_refusal(clean_text)

                # 발언자 검증: 타인 발언 이동 + 이름 교정
                # lg_state meta 대신 user_input에서 직접 추출 (세션 캐시 Router 우회)
                from graph.nodes.router import (
                    _extract_query_speaker_kw,
                    _extract_comparison_subjects,
                )
                _qsk = list(_extract_query_speaker_kw(user_input) or [])
                _comp = _extract_comparison_subjects(user_input) if not _qsk else []
                clean_text, _spk_changed = _validate_speaker_bullets(
                    clean_text, docs, _qsk, _comp or None
                )

                # 비교 쿼리: 인물별 근거 존재 여부 판정 + 결론 attribution 정리
                if _comp:
                    clean_text, _ = _check_per_subject_grounding(clean_text, docs, _comp)

                # 한계 모순 문구 제거 — 반드시 _remove_unlabeled_detail_section 전에
                clean_text, _ = _remove_contradictory_limits(clean_text)

                # 볼드 레이블 없는 세부 근거 섹션 제거
                clean_text, _ = _remove_unlabeled_detail_section(clean_text)

                # 기준 4: 미인용 문장 → ## 한계로 이동
                # _pre_normalize: 헤더+본문 같은 줄 → 분리 후 점수 계산
                score = _grounding_score(_pre_normalize(clean_text))
                if score <= CITE_FULL_THRESHOLD:
                    clean_text, _ = _move_uncited_to_limits(clean_text)
                # 텍스트 변환 후 재채점 (move_uncited_to_limits가 구조를 바꿀 수 있음)
                score = _grounding_score(_pre_normalize(clean_text))

                # 기준 1: grounding 경고 첨부
                if score == 0:
                    grounding_level = "NONE"
                    clean_text = clean_text.rstrip() + _WARN_NONE
                elif score <= CITE_FULL_THRESHOLD:
                    grounding_level = "PARTIAL"
                    # 비교 쿼리 발언자 불일치가 주 원인이면 전용 경고
                    if _comp and _spk_changed:
                        clean_text = clean_text.rstrip() + _WARN_SPEAKER_MISMATCH
                    else:
                        clean_text = clean_text.rstrip() + _WARN_PARTIAL
                else:
                    grounding_level = "FULL"

                disclaimer = "\n\n※ 본 답변은 회의록 기반 정보 정리 결과입니다."
                if disclaimer not in clean_text:
                    clean_text += disclaimer
                _meta = lg_state.get("meta") or {}
                _committee = str(_meta.get("committee") or "").strip()
                clean_text += _confidence_line(docs, grounding_level, _committee)
                clean_text = _renumber_citations(clean_text, lg_state)
                reply = _append_citations_block(clean_text, lg_state)
                _append_message("assistant", reply)

    except Exception as exc:
        short, detail = _format_user_error(exc)
        err_msg = f"{short}\n\n{detail}"
        with st.chat_message("assistant", avatar="🤖"):
            st.error(short)
        _append_message("assistant", err_msg)
        with st.expander("기술적인 오류 내용"):
            st.code(str(exc))

    current_session = st.session_state.chat_sessions[st.session_state.current_session_id]
    if len(current_session['messages']) == 3:
        new_title = user_input[:30] + ("..." if len(user_input) > 30 else "")
        current_session['title'] = new_title
        chat_service.update_session_title(st.session_state.current_session_id, new_title)
    st.rerun()


def _append_message(role: str, content: str) -> None:
    """현재 세션에 메시지 추가"""
    session_id = st.session_state.current_session_id
    timestamp = datetime.now().isoformat()
    
    # SQLite에 메시지 추가
    chat_service.add_message(session_id, role, content)
    
    # 세션 상태에도 추가
    current_session = st.session_state.chat_sessions[session_id]
    current_session['messages'].append({
        "role": role,
        "content": content,
        "timestamp": timestamp
    })


def _load_saved_sessions() -> None:
    """SQLite에서 저장된 세션들을 로드"""
    try:
        sessions = chat_service.get_all_sessions()
        for session in sessions:
            session_id = session['id']
            messages = chat_service.get_session_messages(session_id)
            st.session_state.chat_sessions[session_id] = {
                "title": session['title'],
                "created_at": session['created_at'],
                "messages": messages
            }
    except Exception as e:
        st.error(f"세션 로드 실패: {e}")


def _avatar_for(role: str) -> str:
    return "🧑‍💻" if role == "user" else "🤖"


def _get_langgraph_app():
    if "langgraph_app" not in st.session_state:
        st.session_state.langgraph_app = build_app()
    return st.session_state.langgraph_app

def _llm_setup_banner() -> None:
    ok, msg = llm_env_probe()
    if ok:
        return
    st.warning(msg, icon="⚠️")


def _parse_meeting_iso(d: str) -> date | None:
    s = (d or "").strip()[:10]
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _summary_for_display(quote: str, item: dict, max_len: int = 160) -> str:
    q = (quote or "").strip()
    if not q:
        fb = item.get("title") or item.get("document_name") or item.get("committee") or ""
        q = str(fb).strip() or "—"
    if len(q) <= max_len:
        return q
    return q[:max_len - 3].rstrip() + "..."


def _parse_citations_json(blob: str) -> list[dict] | None:
    """메시지 꼬리에서 JSON 인용 목록 추출. 없거나 깨졌으면 None."""
    blob = blob.strip()
    if RAG_CITATIONS_JSON_BEGIN not in blob:
        return None
    try:
        start = blob.index(RAG_CITATIONS_JSON_BEGIN) + len(RAG_CITATIONS_JSON_BEGIN)
        end = blob.index(RAG_CITATIONS_JSON_END, start)
        return json.loads(blob[start:end])
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _trust_grade(item: dict, ref_d: date) -> str:
    """출처 신뢰도 등급 (날짜와 무관하게 발언자 정보로만 판단).
    ⭐높음: 발언자·날짜 모두 확인
    △보통: 둘 중 하나만 확인
    ▽낮음: 모두 미상
    """
    speaker = (item.get("speaker") or "").strip()
    date_str = item.get("date") or item.get("meeting_date") or ""
    parsed = _parse_meeting_iso(date_str)

    speaker_ok = bool(speaker) and speaker != "발언자 미상"
    date_ok = parsed is not None

    if speaker_ok and date_ok:
        return "⭐ 높음"
    if speaker_ok or date_ok:
        return "△ 보통"
    return "▽ 낮음"


def _render_references_table(citations: list[dict], used_indices: set[int] | None = None, msg_key: str = "") -> None:
    """참고 자료를 표로 정렬해 표시 (본문 [n] ↔ 표 번호).
    used_indices: 본문에서 실제 사용된 [n] 집합 (1-based). None이면 전체 표시.
    """
    ref_d = date.today()
    rows: list[dict] = []
    for idx, item in enumerate(citations, start=1):
        if used_indices is not None and idx not in used_indices:
            continue
        speaker = (item.get("speaker") or "").strip() or "발언자 미상"
        date_disp = item.get("date") or item.get("meeting_date") or "—"
        quote = (item.get("quote") or "").strip()
        summary = _summary_for_display(quote, item)
        url = (item.get("url") or "").strip()
        link_cell = url if url.startswith(("http://", "https://")) else ""

        rows.append(
            {
                "번호": idx,
                "신뢰도": _trust_grade(item, ref_d),
                "회의일": date_disp,
                "발언자": speaker,
                "인용 내용": summary,
                "링크": link_cell,
            }
        )

    if not rows:
        st.caption("본문에서 사용된 인용 출처가 없습니다.")
        return
    st.caption(
        "본문 **`[n]`** 과 **번호** 열이 대응합니다 · 인용 내용은 실제 발언 최대 160자입니다 · "
        "전체 원문은 아래 '인용 청크 원문 보기'에서 확인하세요."
    )
    df = pd.DataFrame(rows)
    has_url = any(r.get("링크") for r in rows)
    link_col_cfg = (
        st.column_config.LinkColumn("원문", display_text="열기", width="small")
        if has_url
        else st.column_config.TextColumn("원문", width="small")
    )
    st.dataframe(
        df,
        column_config={
            "번호": st.column_config.NumberColumn("번호", format="%d", width="small"),
            "신뢰도": st.column_config.TextColumn("신뢰도", width="small"),
            "회의일": st.column_config.TextColumn("회의일", width="small"),
            "발언자": st.column_config.TextColumn("발언자", width="medium"),
            "인용 내용": st.column_config.TextColumn("인용 내용 (실제 발언)", width="large"),
            "링크": link_col_cfg,
        },
        hide_index=True,
        use_container_width=True,
    )

    # 검색 청크 보기
    filtered = [
        (idx, item) for idx, item in enumerate(citations, start=1)
        if (used_indices is None or idx in used_indices) and (item.get("chunk_text") or "").strip()
    ]
    if filtered:
        # 같은 발언자·같은 날짜 인접 청크 병합
        merged = _merge_adjacent_chunks(filtered)
        with st.expander("📄 검색 청크 보기 (발언 원문)", expanded=False):
            st.caption(
                "DB에서 가져온 발언 원문입니다. "
                "같은 발언자·같은 회의의 인접 청크는 자동으로 합쳐 표시합니다. "
                "중복 overlap·메타데이터는 제거됩니다."
            )
            for group in merged:
                indices = group["indices"]
                speaker = group["speaker"]
                date_str = group["date"]
                chunk = group["chunk_text"]

                idx_label = ", ".join(f"[{i}]" for i in indices)
                source_path_str = ""
                if citations and indices:
                    first_idx = indices[0] - 1  # 0-based
                    if 0 <= first_idx < len(citations):
                        ci = citations[first_idx]
                        source_path_str = ci.get("source_path", "")

                header_col, btn_col = st.columns([6, 1])
                with header_col:
                    st.markdown(f"**{idx_label} {speaker}** ({date_str})")
                with btn_col:
                    _render_pdf_download_button(source_path_str, indices, msg_key=msg_key)

                excerpt = _extract_key_sentences(chunk, max_sentences=6)
                if excerpt != chunk:
                    st.text(excerpt)
                    st.caption("↑ 앞쪽 핵심 문장을 발췌했습니다.")
                else:
                    st.text(chunk)

                # 원본 PDF 페이지 인라인 뷰어
                if source_path_str and _FITZ_AVAILABLE:
                    pdf_path = _PROJECT_ROOT / Path(source_path_str.replace("\\", "/"))
                    if pdf_path.exists():
                        ck = "_".join(str(i) for i in indices)
                        show_pg = st.checkbox(
                            "📖 원본 페이지 보기",
                            key=f"show_pg_{msg_key}_{ck}",
                        )
                        if show_pg:
                            with st.spinner("페이지 불러오는 중..."):
                                img_bytes, page_num, matched = _render_chunk_page_image(
                                    str(pdf_path), chunk
                                )
                            if img_bytes:
                                if matched:
                                    st.caption(
                                        f"📄 **{pdf_path.name}** · {page_num}쪽"
                                        " (노란색: 해당 발언)"
                                    )
                                else:
                                    st.caption(
                                        f"📄 **{pdf_path.name}** · {page_num}쪽"
                                        " (발언 위치 자동 탐색 실패 — 전체 파일은 📄 PDF 버튼)"
                                    )
                                st.image(img_bytes, use_container_width=True)
                            else:
                                st.caption("PyMuPDF로 페이지를 렌더링할 수 없습니다.")
                st.divider()


def _append_citations_block(answer: str, state: dict) -> str:
    citations = state.get("citations", [])
    if not citations:
        return answer
    payload = json.dumps(citations, ensure_ascii=False)
    return (
        answer.rstrip()
        + "\n\n"
        + RAG_REF_MARKER
        + "\n"
        + RAG_CITATIONS_JSON_BEGIN
        + payload
        + RAG_CITATIONS_JSON_END
    )


def _normalize_llm_markdown(text: str) -> str:
    """모델이 한 줄에 이어붙인 `##`, 불릿을 줄바꿈으로 분리해 Streamlit 마크다운이 인식하게 한다."""
    t = (text or "").replace("\r\n", "\n").strip()
    if not t:
        return t
    # "...문장. ## 제목" → 헤더가 줄 맨 앞에 오도록
    t = re.sub(r"([.!?。…])\s*(##\s)", r"\1\n\n\2", t)
    t = re.sub(r"(\])\s*(##\s)", r"\1\n\n\2", t)
    # "## 세부 근거 - 첫불릿" 한 줄인 경우
    t = re.sub(r"(##\s*세부\s*근거)\s*-\s+", r"\1\n\n- ", t, flags=re.IGNORECASE)
    # "## 한계 본문" 첫 글자 앞에 빈 줄
    t = re.sub(r"(##\s*한계)\s+([^\n#])", r"\1\n\n\2", t)
    # 문장 끝 다음 불릿 "- "
    t = re.sub(r"\.\s+-\s+", ".\n- ", t)
    t = re.sub(r"\]\s+-\s+", "]\n- ", t)
    return t


def _render_markdown_sections(body: str) -> None:
    """`##` 헤더는 Streamlit subheader로 옮겨 마커(#) 노출을 줄이고 단락을 나눈다."""
    t = _normalize_llm_markdown(body)
    parts = re.split(r"(?m)^(?=## (?![#]))", t)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        first = lines[0].strip()
        rest = lines[1].strip() if len(lines) > 1 else ""
        if first.startswith("##") and not first.startswith("###"):
            title = first.lstrip("#").strip()
            while title.startswith("#"):
                title = title.lstrip("#").strip()
            st.subheader(title)
            if rest:
                st.markdown(rest)
        else:
            st.markdown(part)


def _remove_overlap(a: str, b: str, min_len: int = 30) -> str:
    """b의 앞부분이 a 안에 포함되면 그 부분을 b에서 제거.
    단순 tail-head 비교가 아닌 substring 검색으로 더 넓은 범위 탐지.
    """
    max_check = min(len(b), 300)
    for length in range(max_check, min_len - 1, -1):
        prefix = b[:length]
        if prefix in a:
            return b[length:].lstrip()
    return b


def _merge_adjacent_chunks(
    filtered: list[tuple[int, dict]],
) -> list[dict]:
    """같은 발언자·같은 날짜의 인접 청크를 병합해 반환."""
    if not filtered:
        return []
    groups: list[dict] = []
    for idx, item in filtered:
        speaker = (item.get("speaker") or "미상").strip()
        date_str = (item.get("date") or item.get("meeting_date") or "—").strip()
        chunk = (item.get("chunk_text") or "").strip()
        if (
            groups
            and groups[-1]["speaker"] == speaker
            and groups[-1]["date"] == date_str
        ):
            prev = groups[-1]["chunk_text"]
            extra = _remove_overlap(prev, chunk)
            if extra and extra != chunk:
                groups[-1]["chunk_text"] = prev.rstrip() + " " + extra
            elif not extra:
                pass  # 완전히 포함된 청크 — 무시
            else:
                groups[-1]["chunk_text"] = prev.rstrip() + "\n" + chunk
            groups[-1]["indices"].append(idx)
        else:
            groups.append({"indices": [idx], "speaker": speaker, "date": date_str, "chunk_text": chunk})
    return groups


def _extract_key_sentences(chunk: str, max_sentences: int = 6) -> str:
    """청크가 길면 앞쪽 핵심 문장만 반환 (중복 tail 표시 없이 앞에서 자름)."""
    sents = re.split(r"(?<=[다요임까함됩니겠었했죠네음어]\.)\s*", chunk)
    sents = [s.strip() for s in sents if s.strip()]
    if len(sents) <= max_sentences:
        return chunk
    return " ".join(sents[:max_sentences]) + " …"


def _likms_search_url(committee: str, date_str: str) -> str:
    """국회 회의록 시스템(LIKMS) 검색 URL 생성."""
    base = "https://likms.assembly.go.kr/record/mhs-40-010.do"
    # 날짜에서 연도 추출
    year = date_str[:4] if date_str and len(date_str) >= 4 else ""
    params = []
    if committee:
        params.append(f"searchCommittee={committee}")
    if year:
        params.append(f"searchYear={year}")
    if params:
        return base + "?" + "&".join(params)
    return base


@st.cache_data(show_spinner=False)
def _render_chunk_page_image(pdf_path_str: str, chunk_text: str) -> tuple[bytes, int, bool]:
    """청크가 있는 PDF 페이지를 PNG 이미지로 렌더링.
    반환: (png_bytes, 1-based 페이지 번호, 텍스트 매칭 성공 여부).
    텍스트를 찾지 못하면 1페이지를 fallback으로 반환 (matched=False).
    """
    _FALLBACK = b""  # fitz 없을 때 반환값
    if not _FITZ_AVAILABLE:
        return _FALLBACK, 0, False
    try:
        doc = fitz.open(pdf_path_str)
    except Exception:
        return _FALLBACK, 0, False

    raw = re.sub(r"\s+", " ", chunk_text.strip())
    n = len(raw)
    candidates: list[str] = []
    for start in [0, n // 5, n // 4, n // 3, n // 2]:
        for length in [40, 25, 15]:
            phrase = raw[start : start + length].strip()
            if len(phrase) >= 10 and phrase not in candidates:
                candidates.append(phrase)

    found_page: int | None = None
    found_rects: list = []

    for probe in candidates:
        # 1차: PyMuPDF 네이티브 검색 (레이아웃 기반, 가장 정확)
        for pn in range(len(doc)):
            rects = doc[pn].search_for(probe)
            if rects:
                found_page = pn
                found_rects = rects
                break
        if found_page is not None:
            break
        # 2차: 추출 텍스트 공백 정규화 비교
        norm_probe = re.sub(r"\s+", " ", probe)
        for pn in range(len(doc)):
            if norm_probe in re.sub(r"\s+", " ", doc[pn].get_text()):
                found_page = pn
                break
        if found_page is not None:
            break
        # 3차: 공백 완전 제거 (한국어 PDF 단어 분리 편차 대응)
        no_sp = re.sub(r"\s+", "", probe)
        if len(no_sp) < 8:
            continue
        for pn in range(len(doc)):
            if no_sp in re.sub(r"\s+", "", doc[pn].get_text()):
                found_page = pn
                break
        if found_page is not None:
            break

    matched = found_page is not None
    if not matched:
        # fallback: 1페이지 (표지/목차 건너뜀)
        found_page = min(2, len(doc) - 1)

    page = doc[found_page]
    if found_rects:
        for rect in found_rects:
            annot = page.add_highlight_annot(rect.quad)
            annot.set_colors(stroke=[1, 0.88, 0])
            annot.update()

    mat = fitz.Matrix(1.8, 1.8)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes, found_page + 1, matched


def _render_pdf_download_button(source_path: str, indices: list[int], msg_key: str = "") -> None:
    """로컬 크롤링 PDF 파일을 다운로드 버튼으로 제공.
    source_path가 없거나 파일이 없으면 아무것도 렌더링하지 않는다.
    """
    if not source_path:
        return
    pdf_path = _PROJECT_ROOT / Path(source_path.replace("\\", "/"))
    if not pdf_path.exists():
        return
    idx_part = "_".join(str(i) for i in indices)
    key = f"pdf_dl_{msg_key}_{idx_part}"
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError:
        return
    st.download_button(
        label="📄 PDF",
        data=pdf_bytes,
        file_name=pdf_path.name,
        mime="application/pdf",
        key=key,
    )


def _extract_used_indices(text: str) -> set[int]:
    """본문에서 실제 사용된 [n] 번호 집합 (1-based) 반환."""
    return {int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", text)}


def _renumber_citations(text: str, state: dict) -> str:
    """본문 [n]을 1부터 순서대로 재번호 매기고 state["citations"]도 같이 필터링.
    예: 본문이 [2][3][5]만 사용하면 → [1][2][3]으로 바꾸고 citations도 그 3개만 유지.
    """
    used = _extract_used_indices(text)
    if not used:
        state["citations"] = []  # 인용 없으면 참고자료 테이블 자체를 숨김
        return text
    sorted_used = sorted(used)
    remap = {old: new for new, old in enumerate(sorted_used, start=1)}
    new_text = re.sub(
        r"\[(\d+)\]",
        lambda m: f"[{remap.get(int(m.group(1)), int(m.group(1)))}]",
        text,
    )
    original = state.get("citations") or []
    state["citations"] = [
        original[i - 1]
        for i in sorted_used
        if 1 <= i <= len(original)
    ]
    return new_text


def _render_assistant_markdown(content: str, msg_key: str = "") -> None:
    """본문은 섹션 단위로 정리해 표시, 참고 자료는 펼침 영역."""
    if RAG_REF_MARKER in content:
        main, _, refs = content.partition(RAG_REF_MARKER)
        main = main.strip()
        refs = refs.strip()
        if main:
            _render_markdown_sections(main)
        if refs:
            parsed = _parse_citations_json(refs)
            total = len(parsed) if parsed else 0
            used = _extract_used_indices(main) if parsed else set()
            used_count = len([i for i in used if 1 <= i <= total])
            with st.expander("📚 참고 자료 — 회의록 근거 출처", expanded=True):
                if parsed is not None:
                    if total > used_count > 0:
                        st.info(
                            f"검색된 청크 **{total}개** 검토 → 본문에서 직접 인용한 **{used_count}개** 출처만 표시합니다.  \n"
                            f"나머지 {total - used_count}개는 답변 맥락 파악에 활용했으나 직접 인용되지 않았습니다.",
                            icon="ℹ️",
                        )
                    _render_references_table(parsed, used_indices=used if used else None, msg_key=msg_key)
                else:
                    _render_markdown_sections(refs)
    else:
        _render_markdown_sections(content)


def _format_langgraph_response(state: dict) -> str:
    docs = state.get("reranked") or state.get("retrieved") or []
    llm_kind = state.get("llm_error_kind")
    draft_raw = (state.get("draft_answer") or "").strip()

    if not docs:
        return (
            "**적재된 회의록 데이터에서 관련 청크를 찾지 못했습니다.**\n\n"
            "(검색 단계에서 결과가 0건입니다. 답변 생성 전에 중단되었습니다.)\n\n"
            "**다음을 시도해 보세요.**\n"
            "- 왼쪽에서 위원회 이름을 비우거나 수정해 검색 범위를 넓힙니다.\n"
            "- 「검색 문서 개수(top-k)」를 늘립니다.\n"
            "- 회의일 범위가 너무 좁지 않은지 확인합니다.\n\n"
            "설정을 바꾼 뒤 같은 질문을 다시 보내 보세요."
        )

    if llm_kind == "model_backend" and draft_raw:
        head = (
            "**답변 생성(모델/키) 단계에서 실패했습니다.** "
            "회의록 검색은 문서를 가져온 상태입니다.\n\n"
            f"{draft_raw}\n\n"
            "`.env`의 `OPENAI_API_KEY`, 또는 로컬 경로 `MODEL_DIR_BASE` / `MODEL_DIR_ADAPTER`를 확인하세요."
        )
        return _append_citations_block(head, state)

    if llm_kind == "exception" and draft_raw:
        head = (
            "**답변 생성 중 예외가 발생했습니다.** "
            "회의록 검색 결과는 있으나 모델 처리에서 오류가 났습니다.\n\n"
            f"{draft_raw}"
        )
        return _append_citations_block(head, state)

    answer = draft_raw
    if not answer:
        answer = (
            "모델이 이번 질문에 대한 본문 답변을 만들지 못했습니다. "
            "아래 검색으로 가져온 회의록 참고 자료만 확인해 주세요."
        )
    return _append_citations_block(answer, state)
