from __future__ import annotations
import json
import streamlit as st
from datetime import datetime
from service.chat_service import ChatService
from graph.app_graph import build_app


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
    </style>
    """, unsafe_allow_html=True)



# 예상 질문 목록 (레벨별)
SUGGESTED_QUESTIONS = {
    "beginner": [
        "외교통일위원회 최근 회의의 핵심 쟁점을 쉽게 요약해줘.",
        "특정 회의록에서 누가 어떤 발언을 했는지 알려줘.",
        "최근 회의 일정과 안건 흐름을 간단히 정리해줘.",
    ],
    "intermediate": [
        "같은 안건이 여러 회의에서 어떻게 이어졌는지 비교해줘.",
        "쟁점별로 여야 발언 경향을 정리해줘.",
        "회의록 근거 문장과 함께 요약해줘.",
    ],
    "advanced": [
        "특정 기간 회의록에서 외교 현안의 논점 변화를 추적해줘.",
        "주요 발언자별 주장 패턴을 비교해줘.",
        "위원회별 의제 유사도를 근거와 함께 설명해줘.",
    ],
}

LEVEL_LABEL = {
    "beginner": "초급",
    "intermediate": "중급",
    "advanced": "고급",
}


# 채팅 서비스 초기화
chat_service = ChatService()

def render_chat_panel() -> None:
    """Render interactive chat interface for Q&A."""
    # 버튼 스타일 적용
    change_chat_theme()
    
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
    for message in current_history:
        role = message["role"]
        with chat_container:
            st.chat_message(name=role, avatar=_avatar_for(role)).write(message["content"])

    if st.session_state.get("latest_langgraph_state"):
        with st.expander("LangGraph 상태 (디버그)", expanded=False):
            debug_state = _summarize_state(st.session_state["latest_langgraph_state"])
            st.text_area(
                "state",
                json.dumps(debug_state, ensure_ascii=False, indent=2),
                height=320,
            )

    # 채팅 입력창
    user_input = st.chat_input("질문을 입력하세요.")
    if user_input:
        _handle_user_input(user_input)


def _render_suggested_questions() -> None:
    """예상 질문 버튼들을 렌더링"""
    level_raw = st.session_state.get("user_level") or "beginner"
    level = str(level_raw).lower()
    if level not in SUGGESTED_QUESTIONS:
        level = "beginner"

    display_level = LEVEL_LABEL.get(level, LEVEL_LABEL["beginner"])

    st.markdown(f"### 💡 추천 질문 ({display_level})")
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
    questions = SUGGESTED_QUESTIONS[level]
    for i, question in enumerate(questions):
        col = cols[i % 2]
        with col:
            if st.button(question, key=f"suggested_{level}_{i}", use_container_width=True):
                _handle_user_input(question)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()


def _init_state() -> None:
    """세션 상태 초기화"""
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
        st.session_state.current_session_id = None
        _load_saved_sessions()
    if "user_level" not in st.session_state:
        st.session_state.user_level = st.session_state.get("user_level") or "beginner"
    defaults = [
        ("qa_top_k", 8),
        ("qa_alpha", 0.75),
        ("qa_candidate_multiplier", 50),
        ("qa_use_reranker", False),
        ("qa_balance_speakers", False),
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
            st.selectbox(
                "답변 난이도",
                options=["beginner", "intermediate", "advanced"],
                format_func=lambda k: LEVEL_LABEL.get(k, k),
                key="user_level",
            )
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
        st.write("---")
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


def _handle_user_input(user_input: str) -> None:
    _append_message("user", user_input)
    try:
        app = _get_langgraph_app()
        user_level = str(st.session_state.get("user_level", "intermediate")).lower()
        meta = _build_search_meta_from_session()
        with st.spinner("회의록을 검색하고 답변을 작성하는 중입니다..."):
            lg_state = app.invoke({"question": user_input, "user_level": user_level, "meta": meta})
        assistant_reply = _format_langgraph_response(lg_state)
        st.session_state["latest_langgraph_state"] = lg_state
        print(f"[Chat] assistant_reply={assistant_reply[:200]!r}")
        _append_message("assistant", assistant_reply)
    except Exception as exc:
        short, detail = _format_user_error(exc)
        _append_message("assistant", f"{short}\n\n{detail}")
        with st.expander("기술적인 오류 내용"):
            st.code(str(exc))

    current_session = st.session_state.chat_sessions[st.session_state.current_session_id]
    if len(current_session['messages']) == 3:
        new_title = user_input[:30] + ("..." if len(user_input) > 30 else "")
        current_session['title'] = new_title
        # SQLite에도 제목 업데이트
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


def _summarize_state(state: dict, str_limit: int = 200) -> dict:
    def _summarize(value):
        if isinstance(value, str):
            text = value.strip()
            return text if len(text) <= str_limit else text[:str_limit] + "…"
        if isinstance(value, list):
            items = [_summarize(item) for item in value[:3]]
            if len(value) > 3:
                items.append(f"… (+{len(value) - 3} more)")
            return items
        if isinstance(value, dict):
            preview = list(value.items())[:6]
            return {k: _summarize(v) for k, v in preview}
        return value

    return {k: _summarize(v) for k, v in state.items()}


def _get_langgraph_app():
    if "langgraph_app" not in st.session_state:
        st.session_state.langgraph_app = build_app()
    return st.session_state.langgraph_app

def _format_langgraph_response(state: dict) -> str:
    docs = state.get("reranked") or state.get("retrieved") or []
    if not docs:
        return (
            "관련 회의록을 찾지 못했습니다.\n\n"
            "**다음을 시도해 보세요.**\n"
            "- 왼쪽에서 위원회 이름을 비우거나 수정해 검색 범위를 넓힙니다.\n"
            "- 「검색 문서 개수(top-k)」를 늘립니다.\n"
            "- 회의일 범위가 너무 좁지 않은지 확인합니다.\n\n"
            "설정을 바꾼 뒤 같은 질문을 다시 보내 보세요."
        )

    answer = state.get("draft_answer", "").strip()
    if not answer:
        answer = (
            "모델이 이번 질문에 대한 본문 답변을 만들지 못했습니다. "
            "아래 검색으로 가져온 회의록 참고 자료만 확인해 주세요."
        )
    citations = state.get("citations", [])
    if citations:
        lines = ["\n\n📚 참고 자료"]
        for idx, item in enumerate(citations, start=1):
            source_id = item.get("source_id") or item.get("chunk_id") or "source 미상"
            date = item.get("date") or item.get("meeting_date") or "날짜 미상"
            quote = (item.get("quote") or "").strip()
            if not quote:
                fallback = item.get("title") or item.get("document_name") or item.get("committee") or ""
                quote = str(fallback).strip()[:140]
            url = item.get("url", "")
            line = f"- [{idx}] source={source_id} date={date} quote={quote}"
            if url:
                line += f" {url}"
            lines.append(line)
        answer += "\n".join(lines)
    return answer
