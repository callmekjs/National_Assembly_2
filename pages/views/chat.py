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
    _render_chat_sessions_sidebar()
    
    # # 현재 대화창 제목 표시
    current_session = st.session_state.chat_sessions[st.session_state.current_session_id]
    current_history = current_session['messages']
    if len(current_history) <= 1:
        _render_suggested_questions()

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
    if not st.session_state.current_session_id or st.session_state.current_session_id not in st.session_state.chat_sessions:
        _create_new_session()


def _render_chat_sessions_sidebar() -> None:
    """대화창 관리 사이드바 - 상단에 위치"""
    with st.sidebar:
        # 대화창 관리를 맨 위로 이동
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
            "안녕하세요! 국회 회의록 관련 질문을 입력해 주세요."
        )
        
        # 세션 상태에 추가
        st.session_state.chat_sessions[session_id] = {
            "title": title,
            "created_at": datetime.now().isoformat(),
            "messages": [
                {
                    "role": "assistant",
                    "content": "안녕하세요! 국회 회의록 관련 질문을 입력해 주세요.",
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
        user_level = st.session_state.get("user_level", "intermediate")
        with st.spinner("답변을 준비하고 있습니다..."):
            lg_state = app.invoke({"question": user_input, "user_level": user_level})
        assistant_reply = _format_langgraph_response(lg_state)
        st.session_state["latest_langgraph_state"] = lg_state
        print(f"[Chat] assistant_reply={assistant_reply[:200]!r}")
        _append_message("assistant", assistant_reply)
    except Exception as exc:
        _append_message("assistant", "죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
        st.warning(f"LangGraph 실행 오류: {exc}")

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
    answer = state.get("draft_answer", "").strip()
    if not answer:
        answer = "죄송합니다. 이번 질문에 대한 답변을 생성하지 못했습니다."
    citations = state.get("citations", [])
    if citations:
        lines = ["\n\n📚 참고 자료"]
        for item in citations:
            committee = item.get("committee") or ""
            document_name = item.get("document_name") or ""
            title = item.get("title") or document_name or committee or "출처 미상"
            date = item.get("date") or item.get("meeting_date") or "날짜 미상"
            ref_id = item.get("source_id") or item.get("chunk_id") or "ref"
            url = item.get("url", "")
            line = f"- {title} ({date}) [{ref_id}]"
            if url:
                line += f" {url}"
            lines.append(line)
        answer += "\n".join(lines)
    return answer
